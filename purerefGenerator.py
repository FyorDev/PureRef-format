import purerefReverse as purRev
from PIL import Image
import os
import re
from io import BytesIO

###
#
# This is an example of what you can do with the purerefReverse library
#
# This function will create a neatly organized pureref file from a folder with images
#
###

def generate(readFolder, writeFile):

    purFile = purRev.PurerefObject()

    # All files in folder
    for file in sorted(os.listdir(readFolder), key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split('(\d+)', s)]):
        if file.endswith(".jpg" or ".png"):
            print(file)
            image = Image.open(readFolder + "/" + file)
            image = image.convert(mode="RGB")
            with BytesIO() as f:
                image.save(f, format="PNG", compress_level=7)
            #    image.save(f, format="PNG", optimize=True)
                pngBin = f.getvalue()
            
        purImage = purRev.PurImage()
        purImage.pngBinary = pngBin

        purTransform = purRev.PurGraphicsImageItem()
        purTransform.resetCrop(image.width, image.height)
        purTransform.setName(file.replace(".jpg", ""))
        purTransform.setSource(readFolder + "/" + file)
        purImage.transforms = [purTransform]

        purFile.images.append(purImage)

    # Normalize scale
    totalWidth = 0
    transforms = []
    for image in purFile.images:
        for transform in image.transforms:
            width = transform.points[0][2]*2
            height = transform.points[1][2]*2
            transform.matrix = [float(1000/height), 0.0, 0.0, float(1000/height)]
            totalWidth += float(1000/height)*width
            transforms.append(transform)

    # Divide into rows
    rows = [transforms]
    while len(rows)*2000.0 < totalWidth:
        totalWidth = totalWidth/2.0
        newRows = []
        for row in rows:
            rowLength = totalWidth
            newRow = []
            newRowSecond = []
            for transform in row:
                if rowLength > 0:
                    rowLength -= transform.matrix[0]*transform.points[0][2]*2
                    newRow.append(transform)
                else:
                    newRowSecond.append(transform)
            newRows.append(newRow)
            newRows.append(newRowSecond)
        rows=newRows

    # Normalize row scales and actually place images
    rowNum = 0
    transformYold = 0
    transformY = 0
    for row in rows:
        rowWidth = 0
        for transform in row:
            rowWidth += transform.matrix[0]*transform.points[0][2]*2
        for transform in row:
            transform.matrix[0] *= 20000/rowWidth
            transform.matrix[3] *= 20000/rowWidth
        transformY += 1000 * 20000/rowWidth
        rowWidth = 0
        for transform in row:
            transform.x = rowWidth + transform.matrix[0]*transform.points[0][2]
            rowWidth += transform.matrix[0]*transform.points[0][2]*2
            transform.y = transformYold + transform.matrix[0]*transform.points[1][2]
        transformYold = transformY

        rowNum +=1



    purFile.write(writeFile)
    print("Done! File created")

generate(os.getcwd() + "(folder name)", "newfile.pur")