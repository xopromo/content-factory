import json
import sys
from pathlib import Path

# Insert parent directory at the beginning of path to override global vk_api package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vk_api import VKAPIClient

def test_vk_post():
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
    
    print("Attempting to post to VK wall...")
    params = {
        "message": "🔌 VK Proxy backup test. It works!",
        "owner_id": 374982599  # User ID
    }
    
    res = client.call_vk_api("wall.post", params)
    print("VK wall.post response:", res)

if __name__ == '__main__':
    test_vk_post()
