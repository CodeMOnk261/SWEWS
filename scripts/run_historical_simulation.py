import sys
import os

# Import the send_code function from the client script
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from blender_client import send_code

def main():
    # Python code to be executed dynamically in Blender
    code = f"""
import sys
import os
scripts_dir = r"E:\\Space_Weather_pre\\scripts"
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)
    
import real_data_sim
import importlib
importlib.reload(real_data_sim)

# Rebuild scene for historical data visualizer
real_data_sim.generate_scene()

# Align camera and shading in viewport
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.region_3d.view_perspective = 'CAMERA'
                space.shading.type = 'MATERIAL'

# Play the animation loop
try:
    window = bpy.context.window_manager.windows[0]
    area = [a for a in window.screen.areas if a.type == 'VIEW_3D'][0]
    with bpy.context.temp_override(window=window, area=area, screen=window.screen):
        bpy.ops.screen.animation_play()
except Exception:
    pass
"""

    print("Requesting Blender to build and run the Real-Data Historical Space Weather Simulation...")
    res = send_code(code)
    if res:
        if res.get("error"):
            print("Error updating simulation inside Blender:", res["error"])
            sys.exit(1)
        else:
            if res.get("stdout"):
                print(res["stdout"], end="")
            print("\nSuccessfully launched Real-Data Space Weather Simulation!")
            print("Look at your Blender viewport to watch the May 10-11, 2024 Geomagnetic Storm play out!")
    else:
        print("Failed to communicate with Blender. Is the server running inside Blender?")
        sys.exit(1)

if __name__ == "__main__":
    main()
