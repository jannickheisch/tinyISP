from bleak import BleakScanner, BleakClient
import pygatt
import asyncio

from PySide6.QtGui import QGuiApplication

from PySide6.QtCore import QCoreApplication, QObject, Qt, QByteArray, QLoggingCategory
from PySide6.QtBluetooth import (QBluetoothUuid, QLowEnergyAdvertisingData,
                                 QLowEnergyAdvertisingParameters,
                                 QLowEnergyCharacteristic,
                                 QLowEnergyCharacteristicData,
                                 QLowEnergyController,
                                 QLowEnergyDescriptorData,
                                 QLowEnergyServiceData,
                                 QBluetoothLocalDevice,
                                 QLowEnergyService)

TINYSSB_BLE_REPL_SERVICE_2022 = "6e400001-7646-4b5b-9a50-71becce51558"
TINYSSB_BLE_RX_CHARACTERISTIC = "6e400002-7646-4b5b-9a50-71becce51558"
TINYSSB_BLE_TX_CHARACTERISTIC = "6e400003-7646-4b5b-9a50-71becce51558"


class GATT_SERVER:

    def __init__(self) -> None:
        pass

    def startAdvertising(self):
        QLoggingCategory.setFilterRules("qt.bluetooth* = true")
        #app = QGuiApplication(sys.argv)
        #! [Advertising Data]
        advertising_data = QLowEnergyAdvertisingData()
        advertising_data.setDiscoverability(QLowEnergyAdvertisingData.DiscoverabilityGeneral)
        advertising_data.setIncludePowerLevel(True)
        advertising_data.setLocalName("TEST")
        advertising_data.setServices([QBluetoothUuid(TINYSSB_BLE_REPL_SERVICE_2022)])
    #! [Advertising Data]

    #! [Service Data]
        chRX = QLowEnergyCharacteristicData()
        chRX.setUuid(QBluetoothUuid(TINYSSB_BLE_RX_CHARACTERISTIC))
        chRX.setProperties(QLowEnergyCharacteristic.Write)
        client_config = QLowEnergyDescriptorData(QBluetoothUuid.DescriptorType.ClientCharacteristicConfiguration,
                                                QByteArray(2, 0))
        chRX.addDescriptor(client_config)

        service_data = QLowEnergyServiceData()
        service_data.setType(QLowEnergyServiceData.ServiceTypePrimary)
        service_data.setUuid(QBluetoothUuid(TINYSSB_BLE_REPL_SERVICE_2022))
        service_data.addCharacteristic(chRX)
    #! [Service Data]

    #! [Start Advertising]
        le_controller = QLowEnergyController.createPeripheral()
        service = le_controller.addService(service_data)
        le_controller.startAdvertising(QLowEnergyAdvertisingParameters(),
                                    advertising_data, advertising_data)
        
    #! [Start Advertising]


# auxiliary class for easier management of client connections
class Client:
    def __init__(self, queueSet, clientSet, address) -> None:
        self.queueSet = queueSet
        self.clientSet = clientSet
        self.address = address
        self.queue = asyncio.Queue()

    def __enter__(self):
        self.queueSet.add(self.queue)

        self.clientSet.add(self.address)
        return self.queue
    
    def __exit__(self, type, value, traceback):
        self.queueSet.remove(self.queue)
        self.clientSet.remove(self.address)

class GATT_Server:

    def __init__(self) -> None:
        pass


class BLE_IO:

    def __init__(self) -> None:
        self.scanning = False
        self.stop_event = asyncio.Event()
        self.clients = set()
        self.queues = set()
        self.lock = asyncio.Lock()


    async def scan_callback(self, device, advertisement_data):

        async with self.lock:
            for c in self.clients:
                if c == device.address:
                    return
        
        with Client(self.queues, self.clients, device.address) as queue:
            async with BleakClient(device) as client:
                print("connected", client.address)
                fail_counter = 0

                while True:

                    if not client.is_connected:
                        await client.disconnect()
                        break
                    
                    data = None
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=10)
                    except TimeoutError:
                        pass

                    if data:
                        data = data.encode()

                        try:
                            success = await self.send(client, data)
                            
                            if success:
                                print("send sucessfull", success)
                        except Exception as e:
                            print("Failed:", e)
                            fail_counter += 1    
                    
                    if fail_counter > 5:
                        break

                    if self.stop_event.is_set():
                        print("stop client")
                        break

                print("returning....")
    
    async def send(self, client, data):
        print("Sending:", data, "to", client.address)
        if client.is_connected:
            await client.write_gatt_char(TINYSSB_BLE_RX_CHARACTERISTIC, data, response=False)
            print(f'Data "{data}" sent successfully.')
            return True
        else:
            return False

    def start(self):

        pass

    async def start_scan(self):
        self.stop_event.clear()

        async with  BleakScanner(detection_callback=self.scan_callback, service_uuids=[TINYSSB_BLE_REPL_SERVICE_2022]) as scanner:
            await self.stop_event.wait()

    async def stop_scan(self):
        print("stop scanning")
        self.stop_event.set()

    async def write(client, data):
        data = data.encode()
        await client.write_gatt_char(TINYSSB_BLE_RX_CHARACTERISTIC, data)

    async def user_input_task(self):
        while True:
            # Get input from the user
            user_input = await asyncio.get_event_loop().run_in_executor(None, input, "Enter data: ")
            print("current clients:", len(self.clients))

            if user_input == "end":
                print("stopping...")
                self.stop_event.set()
                self.publish(None)
                # for q in self.out_queues:
                #     await q.put(None)
                

            if self.stop_event.is_set():
                print("leaving")
                break

            # Put the input into the queue
            self.publish(user_input)
            # for q in self.out_queues:
            #     await q.put(user_input)

    def publish(self, data):
        for q in self.queues:
            q.put_nowait(data)

async def start():
    #loop = asyncio.get_event_loop()

    ble = BLE_IO()
    t1 = asyncio.create_task(ble.start_scan())
    t2 = asyncio.create_task(ble.user_input_task())
    await asyncio.gather(t1, t2)

if __name__ == '__main__':
    #asyncio.run(start())
    # app = QCoreApplication([])
    # server = GattServer()
    # server.start()
    # app.exec()
    # app = QGuiApplication()
    s = GATT_SERVER()
    s.startAdvertising()


        


       

