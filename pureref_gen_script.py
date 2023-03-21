import os
import pureref_gen

####################################################################################################
# Just run this with "python pureref_gen_script.py" in your command line inside the PureRef-format
# folder. It will generate a folder for input (Artists) and output (Purs) for you.
# Then you can put folders with images in the Artists folder and run "python pureref_gen_script.py"
# again to generate the Purs.
####################################################################################################

# This is where you put folders with JPG or PNG images
if not os.path.exists(os.getcwd() + "/Artists/"):
    os.mkdir(os.getcwd() + "/Artists/")

# This is where PureRef files come out
if not os.path.exists(os.getcwd() + "/Purs/"):
    os.mkdir(os.getcwd() + "/Purs/")

# Turn all folders with images in Artists/ into .pur files in Purs/
# Unless the .pur already exists, so you can edit it
# If you want to regenerate it, you need to delete the .pur file
for folder in os.listdir(os.getcwd() + "/Artists"):
    if not os.path.exists(os.getcwd() + "/Purs/" + folder + ".pur"):
        print("Creating " + folder + ".pur")
        pureref_gen.generate(os.getcwd() + "/Artists/" + folder, os.getcwd() + "/Purs/" + folder + ".pur")
    else:
        print("File already exists, skipping " + folder)

# The file will say it has a "load error", just press "Open Anyway (Unsafe)"
# This is only because the checksum to check for corruption is not generated correctly
# Which is not a problem, I simply don't know how this checksum is generated
# Save the file once and the error will be gone
