A script for Autodesk's Flame applications to import planar tracking data from Boris FX's Mocha. 
The four corners of a planar track can be brought in either as a perspective grid in Action, GMask Tracer, 
and Image nodes, or as the UV points of a bilinear surface in an Action node.

To use:
    
    --In Mocha, set the s-box corners to where you'd like the corners of your perspective grid or surface to live.

    --Export track as 'Autodesk IFFFSE Point Tracker Data (*.ascii)

    --In Flame, right click on the schematic background of an action/gmask tracer/image node

    --From the 'Import Mocha Track' menu, select desired import type

To install:

    Copy package into /opt/Autodesk/shared/python
