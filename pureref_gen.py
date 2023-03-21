import purformat
from PIL import Image
import os
import re
from io import BytesIO

####################################################################################################
# This function will create a neatly organized .pur (PureRef) file from a folder with PNG or JPG images
# It is used in pureref_gen_script.py to create .pur files from all folders in Artists/
####################################################################################################


def generate(read_folder, write_file):

    # Initialize an empty .pur file which will hold objects for images with transforms(1, n), and text
    pur_file = purformat.PurFile()

    # Natural sort https://stackoverflow.com/a/341745
    # For example: 0.jpg, 2.jpg, 10.jpg, 100.jpg
    # Instead of: 0.jpg, 10.jpg, 100.jpg, 2.jpg
    def natural_keys(text):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]

    # All images in read_folder will be added to pur_file
    # The images will be sorted using natural sort
    # So you can number them to control the order
    files = sorted(os.listdir(read_folder), key=natural_keys)
    if len(files) == 0:
        print("Skipping, no images found in " + read_folder)
        return

    for file in files:
        if not (file.endswith(".jpg") or file.endswith(".jpeg") or file.endswith(".png")):
            continue

        print(file)
        image = Image.open(read_folder + "/" + file)
        image = image.convert(mode="RGB")
        with BytesIO() as f:
            image.save(f, format="PNG", compress_level=7)  # TODO: research why PureRef saves PNG differently sometimes
            png_bin = f.getvalue()  # convert to bytes

        pur_image = purformat.PurImage()
        # PurImage doesn't save PIL images but raw PNG data because sometimes the binary data is actually a reference to
        # the transform of another image, in which case it is a duplicate.
        # So it's not always a PNG, and this is the easiest way to handle it. Might be worth changing one day.
        pur_image.pngBinary = png_bin  # save the image as PNG binary

        pur_transform = purformat.PurGraphicsImageItem()
        pur_transform.reset_crop(image.width, image.height)
        pur_transform.name = file.replace(".jpg", "")
        pur_transform.source = read_folder + "/" + file
        pur_image.transforms = [pur_transform]  # The first transform is the original one, the rest are duplicates
        # If this is somehow messed up, it doesn't matter. Another transform will be made the "original" one.

        pur_file.images.append(pur_image)

    # Normalize Y scale to 1000
    total_width = 0  # Used to divide into rows
    transforms = []  # References to all transforms, to order them. Still in natural order.
    for image in pur_file.images:
        for transform in image.transforms:
            width = transform.points[0][2]*2
            height = transform.points[1][2]*2
            transform.matrix = [float(1000/height), 0.0, 0.0, float(1000/height)]
            total_width += float(1000/height)*width
            transforms.append(transform)  # Reference to the transform in the image. Still inside an image.

    # Divide into rows by cutting in half until it is rectangular enough
    rows = [transforms]  # Initially one row, list of rows with so far only one list of transforms.
    while len(rows)*2000.0 < total_width:  # while more wide than tall, eventually making a decent rectangle
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

    # Normalize row widths and actually place images, this makes everything line up perfectly.
    transform_y_old = 0
    transform_y = 0
    for row in rows:
        row_width = 1  # 1 to avoid division by zero
        for transform in row:
            row_width += transform.matrix[0]*transform.points[0][2]*2
        for transform in row:
            transform.matrix[0] *= 20000/row_width
            transform.matrix[3] *= 20000/row_width
        transform_y += 1000 * 20000/row_width
        row_width = 1  # 1 to avoid division by zero
        for transform in row:
            transform.x = row_width + transform.matrix[0]*transform.points[0][2]
            row_width += transform.matrix[0]*transform.points[0][2]*2
            transform.y = transform_y_old + transform.matrix[0]*transform.points[1][2]
        transform_y_old = transform_y

    pur_file.write(write_file)
    print("Done! File created")
