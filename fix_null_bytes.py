import os
import sys

def fix_null_bytes(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    if b'\x00' in content:
                        print(f"Found null bytes in {file_path}")
                        clean_content = content.replace(b'\x00', b'')
                        with open(file_path, 'wb') as f:
                            f.write(clean_content)
                        print(f"Fixed {file_path}")
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    fix_null_bytes(os.path.dirname(os.path.abspath(__file__)))
    print("Finished checking files")
