import json
import sys
from pathlib import Path

# Insert parent directory at the beginning of path to override global vk_api package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vk_api import VKAPIClient

def test_vk():
    # Load vk token from vk_config.json
    config_path = Path(__file__).parent.parent.parent / "vk_config.json"
    if not config_path.exists():
        print("vk_config.json not found")
        return
        
    config = json.loads(config_path.read_text(encoding="utf-8"))
    token = config.get("token")
    if not token:
        print("VK Token not found in config")
        return
        
    client = VKAPIClient(token)
    
    # Check who we are
    print("Calling users.get...")
    res = client.call_vk_api("users.get", {})
    print("VK Response:", res)

if __name__ == '__main__':
    test_vk()
