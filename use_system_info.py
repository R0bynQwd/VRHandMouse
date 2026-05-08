import json
import os

def display_report():
    if not os.path.exists('system_info.json'):
        print("Eroare: system_info.json nu exista. Ruleaza mai intai identify_system.py.")
        return

    with open('system_info.json', 'r') as f:
        data = json.load(f)

    print("="*40)
    print("      RAPORT COMPONENTE SISTEM")
    print("="*40)
    
    # OS
    print(f"Sistem de Operare: {data['os']['system']} {data['os']['release']}")
    print(f"Arhitectura: {data['os']['architecture']}")
    
    # CPU
    print(f"\nProcesor: {data['cpu']['processor']}")
    print(f"Nuclee: {data['cpu']['physical_cores']} fizice, {data['cpu']['total_cores']} logice")
    
    # RAM
    print(f"\nMemorie RAM:")
    print(f"  Total: {data['memory']['total']}")
    print(f"  Utilizat: {data['memory']['used']} ({data['memory']['percentage']}%)")
    
    # GPU
    print(f"\nPlaca Video (GPU):")
    if isinstance(data['gpu'], list):
        for gpu in data['gpu']:
            print(f"  - {gpu}")
    else:
        print(f"  - {data['gpu']}")
        
    # Disk
    print(f"\nPartitii principale:")
    for disk in data['disks']:
        if disk['total'] != "0.00B": # Skip empty drives
            print(f"  - {disk['device']} ({disk['mountpoint']}): {disk['free']} liberi din {disk['total']}")

    print("="*40)
    print("Analiza completa.")

if __name__ == "__main__":
    display_report()
