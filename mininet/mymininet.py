import random
import csv
import time
import numpy as np
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.topo import Topo
from mininet.link import TCLink
import re

class CloudServer:
    def __init__(self, id, base_cpu, base_bw):
        self.id = id
        self.cpu_usage = {h: max(0.1, min(1.0, np.random.normal(base_cpu, 0.1))) for h in range(24)}
        self.bandwidth = {h: max(100, min(1000, np.random.normal(base_bw, 50))) for h in range(24)}
        self.latency = {h: max(1, min(100, np.random.normal(20, 5))) for h in range(24)}

    def get_features(self, hour):
        return [self.cpu_usage[hour], self.bandwidth[hour], self.latency[hour]]

class Device:
    def __init__(self, id, cpu, bw, delay, loss, self_processing_power):
        self.id = id
        self.cpu = cpu
        self.bandwidth = bw
        self.delay = delay
        self.loss = loss
        self.self_processing_power = self_processing_power

    def get_features(self):
        return [self.cpu, self.bandwidth, self.delay, self.loss, self.self_processing_power]

class CustomTopo(Topo):
    def build(self, cloud_servers, devices):
        switch = self.addSwitch('s1')
        
        for cloud in cloud_servers:
            self.addHost(f'cloud{cloud.id}')
            self.addLink(f'cloud{cloud.id}', switch, 
                         bw=cloud.bandwidth[0], delay=f'{cloud.latency[0]}ms')
        
        for device in devices:
            self.addHost(f'device{device.id}')
            self.addLink(f'device{device.id}', switch, 
                         bw=device.bandwidth, delay=f'{device.delay}ms', loss=device.loss)

def create_network(num_clouds, num_devices):
    cloud_servers = [CloudServer(i+1, random.uniform(0.5, 0.8), random.uniform(500, 800)) for i in range(num_clouds)]
    devices = [Device(i+1, random.uniform(0.1, 0.5), random.uniform(10, 100), 
                      random.uniform(1, 50), random.uniform(0, 5),
                      random.uniform(0.1, 0.3))  # 자체 처리 능력을 낮게 설정
               for i in range(num_devices)]
    
    topo = CustomTopo(cloud_servers, devices)
    net = Mininet(topo=topo, controller=OVSController, link=TCLink)
    return net, cloud_servers, devices

def get_network_activity(hour):
    activity = {
        0: 0.2, 1: 0.1, 2: 0.1, 3: 0.1, 4: 0.2, 5: 0.3,
        6: 0.4, 7: 0.6, 8: 0.8, 9: 0.9, 10: 0.9, 11: 0.9,
        12: 0.8, 13: 0.7, 14: 0.8, 15: 0.9, 16: 1.0, 17: 1.0,
        18: 0.9, 19: 0.8, 20: 0.7, 21: 0.6, 22: 0.5, 23: 0.3
    }
    return activity[hour]

def measure_performance(net, src, dst):
    iperf_result = src.cmd(f'iperf -c {dst.IP()} -t 5')
    bandwidth = 0.0
    match = re.search(r'(\d+(\.\d+)?) ([MGK])bits/sec', iperf_result)
    if match:
        value, unit = float(match.group(1)), match.group(3)
        if unit == 'G':
            bandwidth = value * 1000
        elif unit == 'M':
            bandwidth = value
        elif unit == 'K':
            bandwidth = value / 1000
    
    ping_result = src.cmd(f'ping -c 10 {dst.IP()}')
    delay_match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms', ping_result)
    delay = float(delay_match.group(1)) if delay_match else 0.0
    
    loss_match = re.search(r'(\d+)% packet loss', ping_result)
    loss = float(loss_match.group(1)) if loss_match else 0.0
    
    return bandwidth, delay, loss

def calculate_rating(bandwidth, delay, loss):
    norm_bandwidth = bandwidth / 100
    norm_delay = delay / 100
    norm_loss = loss / 100
    rating = 5 * (0.2 * norm_bandwidth + 0.4 * (1 - norm_delay) + 0.4 * (1 - norm_loss))
    return round(max(0, min(5, rating)), 2)

def select_best_cloud(net, device, cloud_servers, cloud_loads, hour):
    best_entity = None
    best_score = float('-inf')
    best_rating = 0
    best_bandwidth = 0
    best_delay = 0
    best_loss = 0
    activity = get_network_activity(hour)
    
    for cloud in cloud_servers:
        bandwidth, delay, loss = measure_performance(net, net.get(f'device{device.id}'), net.get(f'cloud{cloud.id}'))
        rating = calculate_rating(bandwidth, delay, loss)
        performance_score = (bandwidth / 100) - (delay / 100) - (loss / 10)
        
        total_load = sum(cloud_loads.values())
        if total_load == 0:
            load_score = 1
        else:
            load_score = 1 - (cloud_loads[cloud.id] / total_load)
        
        if activity > 0.7:
            score = performance_score * 0.4 + load_score * 0.6
        else:
            score = performance_score * 0.7 + load_score * 0.3
        
        if score > best_score:
            best_score = score
            best_entity = cloud
            best_rating = rating
            best_bandwidth = bandwidth
            best_delay = delay
            best_loss = loss

    # 최악의 상황에서만 'self' 선택
    self_score = device.self_processing_power - (device.cpu * 0.2)
    self_rating = calculate_rating(device.bandwidth, device.delay, device.loss)
    
    if self_score > best_score and best_rating < 1.0:  # 매우 낮은 rating일 때만 self 선택
        best_entity = 'self'
        best_rating = self_rating
        best_bandwidth = device.bandwidth
        best_delay = device.delay
        best_loss = device.loss

    return best_entity, best_bandwidth, best_delay, best_loss, best_rating

def save_characteristics(devices, cloud_servers):
    with open('device_characteristics.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Device ID', 'CPU', 'Bandwidth', 'Delay', 'Loss', 'Self Processing Power'])
        for device in devices:
            writer.writerow([device.id] + device.get_features())

    with open('cloud_characteristics.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Cloud ID'] + ['CPU_' + str(h) for h in range(24)] + 
                        ['Bandwidth_' + str(h) for h in range(24)] + 
                        ['Latency_' + str(h) for h in range(24)])
        for cloud in cloud_servers:
            row = [cloud.id]
            for h in range(24):
                row.extend(cloud.get_features(h))
            writer.writerow(row)

    print("Device and cloud characteristics saved to CSV files.")

def run_simulation(net, cloud_servers, devices, duration=1440, interval=10):
    print("Starting network simulation...")
    start_time = time.time()
    cloud_loads = {cloud.id: 0 for cloud in cloud_servers}
    
    with open('simulation_results.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Hour', 'Device', 'Selected Entity', 'Bandwidth', 'Delay', 'Loss', 'Rating',
                         'Device CPU', 'Device BW', 'Device Delay', 'Device Loss', 'Device Self Processing',
                         'Cloud CPU Usage', 'Cloud BW', 'Cloud Latency', 'Network Activity'])
        
        cycle_count = 0
        while time.time() - start_time < duration * 60:  # Duration in minutes
            cycle_count += 1
            current_time = time.time() - start_time
            simulated_hour = int((current_time / 600) % 24)  # 600 seconds (10 minutes) represent 1 hour
            activity = get_network_activity(simulated_hour)
            
            print(f"Simulation cycle {cycle_count} - Simulated hour: {simulated_hour}, Network activity: {activity:.2f}")
            
            for device in devices:
                best_entity, bandwidth, delay, loss, rating = select_best_cloud(net, device, cloud_servers, cloud_loads, simulated_hour)
                
                if best_entity == 'self':
                    selected_entity = 'self'
                    cloud_features = [0, 0, 0]  # 자체 처리 시 클라우드 특성은 0으로 설정
                else:
                    selected_entity = f'cloud{best_entity.id}'
                    cloud_loads[best_entity.id] += 1
                    cloud_features = best_entity.get_features(simulated_hour)
                
                device_features = device.get_features()
                
                row = [current_time, simulated_hour, f'device{device.id}', selected_entity,
                       bandwidth, delay, loss, rating] + device_features + cloud_features + [activity]
                writer.writerow(row)
                
                print(f"  Device {device.id} connected to {selected_entity} - Bandwidth: {bandwidth:.2f}, Delay: {delay:.2f}, Loss: {loss:.2f}, Rating: {rating:.2f}")
                print(f"  Saved row: {row}")
            
            print(f"Cloud loads after cycle {cycle_count}: {cloud_loads}")
            print(f"Time elapsed: {current_time:.2f} seconds")
            print("--------------------")
            
            time.sleep(interval)
    
    print(f"Simulation completed after {cycle_count} cycles. Results saved in 'simulation_results.csv'")

if __name__ == '__main__':
    num_clouds = 5
    num_devices = 15
    
    print(f"Initializing simulation with {num_clouds} cloud servers and {num_devices} devices...")
    net, cloud_servers, devices = create_network(num_clouds, num_devices)
    
    save_characteristics(devices, cloud_servers)
    
    try:
        net.start()
        run_simulation(net, cloud_servers, devices)
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        net.stop()
        print("\nSimulation ended. Check 'simulation_results.csv' for detailed results.")