import os
import shutil

def find_and_copy():
    # Search in C:\Users
    print("Searching for tg_session.session...")
    target_name = "tg_session.session"
    found_paths = []
    
    for root, dirs, files in os.walk(r"C:\Users"):
        if target_name in files:
            full_path = os.path.join(root, target_name)
            print(f"Found: {full_path}")
            found_paths.append(full_path)
            
    if not found_paths:
        print("No tg_session.session found!")
        return
        
    # Copy the first found one to C:\Users\асус\telethon\tg_session.session
    # Wait, let's find the correct destination: we can find it relative to C:\Users\асус
    # Let's look for C:\Users\*\telethon
    dest_dir = None
    for root, dirs, files in os.walk(r"C:\Users"):
        if "telethon" in dirs and "Desktop" in dirs:
            dest_dir = os.path.join(root, "telethon")
            print(f"Found destination: {dest_dir}")
            break
            
    if not dest_dir:
        # Fallback to C:\Users\асус\telethon if exists
        dest_dir = r"C:\Users\асус\telethon"
        
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, "tg_session.session")
    
    # Try copying
    shutil.copy(found_paths[0], dest_path)
    print(f"Successfully copied {found_paths[0]} to {dest_path}")

if __name__ == "__main__":
    find_and_copy()
