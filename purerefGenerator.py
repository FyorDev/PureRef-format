import purerefReverse
from PIL import Image
import os
import re
from io import BytesIO

####################################################################################################
# This function will create a neatly organized .pur (PureRef) file from a folder with PNG or JPG images
# It is used in purerefArtistGenerator.py to create .pur files from all folders in Artists/
####################################################################################################


def generate(read_folder, write_file):

    # Initialize an empty .pur file which has objects for images with transforms, and text
    pur_file = purerefReverse.PurFile()

    # Natural sort
    # For example: 0.jpg, 2.jpg, 10.jpg, 100.jpg
    # Instead of: 0.jpg, 10.jpg, 100.jpg, 2.jpg
    def natural_keys(text):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]

    # All images in read_folder will be added to the .pur file
    # The images will be sorted using natural sort https://stackoverflow.com/a/341745
    # So you can number them to control the order
    for file in sorted(os.listdir(read_folder), key=natural_keys):
        if file.endswith(".jpg") or file.endswith(".jpeg") or file.endswith(".png"):
            print(file)
            image = Image.open(read_folder + "/" + file)
            image = image.convert(mode="RGB")
            with BytesIO() as f:
                image.save(f, format="PNG", compress_level=7)
                png_bin = f.getvalue()

            pur_image = purerefReverse.PurImage()
            pur_image.pngBinary = png_bin

            pur_transform = purerefReverse.PurGraphicsImageItem()
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
        row_width = 1
        for transform in row:
            row_width += transform.matrix[0]*transform.points[0][2]*2
        for transform in row:
            transform.matrix[0] *= 20000/row_width
            transform.matrix[3] *= 20000/row_width
        transform_y += 1000 * 20000/row_width
        row_width = 1
        for transform in row:
            transform.x = row_width + transform.matrix[0]*transform.points[0][2]
            row_width += transform.matrix[0]*transform.points[0][2]*2
            transform.y = transform_y_old + transform.matrix[0]*transform.points[1][2]
        transform_y_old = transform_y

    pur_file.write(write_file)
    print("Done! File created")
