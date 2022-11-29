import os
import purerefGenerator

for folder in os.listdir(os.getcwd() + "/Artists"):
    if not os.path.exists(os.getcwd() + "/Purs/" + folder + ".pur"):
        print("Creating " + folder)
        purerefGenerator.generate(os.getcwd() + "/Artists/" + folder, os.getcwd() + "/Purs/" + folder + ".pur")
    else:
        print("File already exists, skipping " + folder)
