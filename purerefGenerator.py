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


def generate(read_folder, write_file):

    pur_file = purRev.PurFile()

    # All files in folder
    for file in sorted(os.listdir(read_folder), key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split('(\d+)', s)]):
        if file.endswith(".jpg" or ".png"):
            print(file)
            image = Image.open(read_folder + "/" + file)
            image = image.convert(mode="RGB")
            with BytesIO() as f:
                image.save(f, format="PNG", compress_level=7)
                png_bin = f.getvalue()

            pur_image = purRev.PurImage()
            pur_image.pngBinary = png_bin

            pur_transform = purRev.PurGraphicsImageItem()
            pur_transform.reset_crop(image.width, image.height)
            pur_transform.set_name(file.replace(".jpg", ""))
            pur_transform.set_source(read_folder + "/" + file)
            pur_image.transforms = [pur_transform]

            pur_file.images.append(pur_image)

    # Normalize scale
    total_width = 0
    transforms = []
    for image in pur_file.images:
        for transform in image.transforms:
            width = transform.points[0][2]*2
            height = transform.points[1][2]*2
            transform.matrix = [float(1000/height), 0.0, 0.0, float(1000/height)]
            total_width += float(1000/height)*width
            transforms.append(transform)

    # Prevent row_width from dividing by 0 later
    if len(transforms) <= 1:
        pur_file.write(write_file)
        print("Done! File created with one or less images")
        return

    # Divide into rows
    rows = [transforms]
    while len(rows)*2000.0 < total_width:
        total_width = total_width/2.0
        new_rows = []
        for row in rows:
            row_length = total_width
            new_row = []
            new_row_second = []
            for transform in row:
                if row_length > 0:
                    row_length -= transform.matrix[0]*transform.points[0][2]*2
                    new_row.append(transform)
                else:
                    new_row_second.append(transform)
            new_rows.append(new_row)
            new_rows.append(new_row_second)
        rows = new_rows

    # Normalize row scales and actually place images
    transform_y_old = 0
    transform_y = 0
    for row in rows:
        row_width = 0
        for transform in row:
            row_width += transform.matrix[0]*transform.points[0][2]*2
        for transform in row:
            transform.matrix[0] *= 20000/row_width
            transform.matrix[3] *= 20000/row_width
        transform_y += 1000 * 20000/row_width
        row_width = 0
        for transform in row:
            transform.x = row_width + transform.matrix[0]*transform.points[0][2]
            row_width += transform.matrix[0]*transform.points[0][2]*2
            transform.y = transform_y_old + transform.matrix[0]*transform.points[1][2]
        transform_y_old = transform_y

    pur_file.write(write_file)
    print("Done! File created")