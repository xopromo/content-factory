import json
import sys
import time
from pathlib import Path

# Insert parent directory at the beginning of path to override global vk_api package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vk_api import VKAPIClient

def test_vk_edit():
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
    user_id = 374982599
    
    # 1. Post new message
    print("Posting initial message...")
    res = client.call_vk_api("wall.post", {
        "message": "🔌 VK Proxy backup test - Initial Post",
        "owner_id": user_id
    })
    print("wall.post response:", res)
    
    if "response" in res and "post_id" in res["response"]:
        post_id = res["response"]["post_id"]
        print(f"Created post: {post_id}. Waiting 3 seconds before editing...")
        time.sleep(3.0)
        
        # 2. Edit message
        print(f"Editing post {post_id}...")
        edit_res = client.call_vk_api("wall.edit", {
            "post_id": post_id,
            "message": "🔌 VK Proxy backup test - UPDATED SUCCESSFULLY!\nThis text is edited in-place.",
            "owner_id": user_id
        })
        print("wall.edit response:", edit_res)
        
        # 3. Clean up (delete the post so we don't leave garbage)
        print("Cleaning up (deleting post)...")
        del_res = client.call_vk_api("wall.delete", {
            "post_id": post_id,
            "owner_id": user_id
        })
        print("wall.delete response:", del_res)

if __name__ == '__main__':
    test_vk_edit()
