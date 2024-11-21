# Copyright (c) 2022-2024 Contributors to the Eclipse Foundation
#
# This program and the accompanying materials are made available under the
# terms of the Apache License, Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""A sample skeleton vehicle app."""

import asyncio
import json
import logging
import signal

import paho.mqtt.client as mqtt
import websockets
from vehicle import Vehicle, vehicle  # type: ignore
from velocitas_sdk.util.log import (  # type: ignore
    get_opentelemetry_log_factory,
    get_opentelemetry_log_format,
)
from velocitas_sdk.vdb.reply import DataPointReply
from velocitas_sdk.vehicle_app import VehicleApp, subscribe_topic

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "vehicle/accident"


# Configure the VehicleApp logger with the necessary log config and level.
logging.setLogRecordFactory(get_opentelemetry_log_factory())
logging.basicConfig(format=get_opentelemetry_log_format())
logging.getLogger().setLevel("DEBUG")
logger = logging.getLogger(__name__)

GET_SPEED_REQUEST_TOPIC = "APT/getSpeed"
GET_SPEED_RESPONSE_TOPIC = "APT/getSpeed/response"
DATABROKER_SUBSCRIPTION_TOPIC = "APT/currentSpeed"
ACCIDENT_REQUEST_TOPIC = "APT/accident"
ACCIDENT_RESPONSE_TOPIC = "APT/accident/response"


connected_clients = set()


async def websocket_handler(websocket):
    print("websocket_handler !!!!!")
    connected_clients.add(websocket)
    print(connected_clients)
    print("################")
    try:
        async for message in websocket:
            print(f"Received from client: {message}")
            await asyncio.wait([client.send(message) for client in connected_clients])
    except websockets.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected_clients.remove(websocket)
        print("Client removed from connected_clients")


async def start_websocket_server():
    server = await websockets.serve(websocket_handler, "0.0.0.0", 8765)
    print("WebSocket server started on ws://0.0.0.0:8765")
    await server.wait_closed()


class APT(VehicleApp):
    def __init__(self, vehicle_client: Vehicle):
        super().__init__()
        self.Vehicle = vehicle_client
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.mqtt_client.loop_start()

    async def on_start(self):
        """Run when the vehicle app starts"""
        # This method will be called by the SDK when the connection to the
        # Vehicle DataBroker is ready.
        # Here you can subscribe for the Vehicle Signals update (e.g. Vehicle Speed).
        await self.Vehicle.Speed.subscribe(self.on_speed_change)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT Broker!")
        else:
            logger.error("Failed to connect, return code %d\n", rc)

    async def handle_accident_event(self):
        accident_data = {
            "event": "accident",
            "vehicle_id": "your_vehicle_id",
            "timestamp": "2023-10-01T12:00:00Z",
        }
        self.mqtt_client.publish(MQTT_TOPIC, json.dumps(accident_data))
        logger.info("Accident event published to MQTT")

    async def on_speed_change(self, data: DataPointReply):
        """The on_speed_change callback, this will be executed when receiving a new
        vehicle signal updates."""
        vehicle_speed = data.get(self.Vehicle.Speed).value

        await self.publish_event(
            DATABROKER_SUBSCRIPTION_TOPIC,
            json.dumps({"speed": vehicle_speed}),
        )

    @subscribe_topic(GET_SPEED_REQUEST_TOPIC)
    async def on_get_speed_request_received(self, data: str) -> None:
        """The subscribe_topic annotation is used to subscribe for incoming
        PubSub events, e.g. MQTT event for GET_SPEED_REQUEST_TOPIC.
        """
        logger.debug(
            "PubSub event for the Topic: %s -> is received with the data: %s",
            GET_SPEED_REQUEST_TOPIC,
            data,
        )

        vehicle_speed = (await self.Vehicle.Speed.get()).value
        await self.publish_event(
            GET_SPEED_RESPONSE_TOPIC,
            json.dumps(
                {
                    "result": {
                        "status": 0,
                        "message": f"""Current Speed = {vehicle_speed}""",
                    },
                }
            ),
        )

    @subscribe_topic(ACCIDENT_REQUEST_TOPIC)
    async def on_get_car_accident_received(self, data: str) -> None:
        """The subscribe_topic annotation is used to subscribe for incoming
        PubSub events, e.g. MQTT event for ACCIDENT_REQUEST_TOPIC.
        """
        logger.debug(
            "PubSub event for the Topic: %s -> is received with the data: %s",
            ACCIDENT_REQUEST_TOPIC,
            data,
        )

        await self.publish_event(
            ACCIDENT_RESPONSE_TOPIC,
            json.dumps(
                {
                    "result": {
                        "status": 0,
                        "message": f"""Received Accident Data: {data}""",
                    },
                }
            ),
        )
        if connected_clients:
            message = json.dumps(
                {
                    "type": "accident",
                    "data": data,
                }
            )
            await asyncio.wait([client.send(message) for client in connected_clients])


async def main():
    """Main function"""
    logger.info("Starting APT app...")
    vehicle_app = APT(vehicle)
    # await vehicle_app.run()
    await asyncio.gather(vehicle_app.run(), start_websocket_server())


LOOP = asyncio.get_event_loop()
LOOP.add_signal_handler(signal.SIGTERM, LOOP.stop)
LOOP.run_until_complete(main())
LOOP.close()
