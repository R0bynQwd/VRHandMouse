import platform
import psutil
import json
import os
import subprocess

def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_system_info():
    info = {}
    
    # OS Info
    info['os'] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine()
    }
    
    # CPU Info
    cpufreq = psutil.cpu_freq()
    info['cpu'] = {
        "physical_cores": psutil.cpu_count(logical=False),
        "total_cores": psutil.cpu_count(logical=True),
        "max_frequency": f"{cpufreq.max:.2f}Mhz" if cpufreq else "N/A",
        "processor": platform.processor()
    }
    
    # Memory Info
    svmem = psutil.virtual_memory()
    info['memory'] = {
        "total": get_size(svmem.total),
        "available": get_size(svmem.available),
        "used": get_size(svmem.used),
        "percentage": svmem.percent
    }
    
    # Disk Info
    partitions = psutil.disk_partitions()
    info['disks'] = []
    for partition in partitions:
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
            info['disks'].append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "file_system": partition.fstype,
                "total": get_size(partition_usage.total),
                "used": get_size(partition_usage.used),
                "free": get_size(partition_usage.free),
                "percentage": partition_usage.percent
            })
        except PermissionError:
            continue

    # GPU Info (Basic attempt via wmic on Windows)
    try:
        if platform.system() == "Windows":
            gpu_info = subprocess.check_output("wmic path win32_VideoController get name", shell=True).decode()
            gpus = [line.strip() for line in gpu_info.split('\n') if line.strip() and "Name" not in line]
            info['gpu'] = gpus
    except Exception:
        info['gpu'] = "N/A"

    return info

if __name__ == "__main__":
    system_data = get_system_info()
    with open('system_info.json', 'w') as f:
        json.dump(system_data, f, indent=4)
    print("Informatiile despre sistem au fost salvate in system_info.json")
