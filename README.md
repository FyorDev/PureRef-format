# PureRef-format  

A Python script to automatically generate organised PureRef (1.10/1.11.1) .pur files from folders of images, and a module you can use to convert .pur files to/from any other file format.

### Video
[![Watch the video](https://img.youtube.com/vi/31lsz3JNtCU/hqdefault.jpg)](https://youtu.be/31lsz3JNtCU)

### Usage
You will need to install Python if you don't have it already (I use 3.8.10), be sure to enable the option to add it to your PATH during installation (for Windows users).  
Navigate to the PureRef-format folder, and in a command prompt type: `python pureref_gen_script.py`  
Without arguments, this will create new folders called "Artists" and "Purs", add folders with images to the "Artists" folder and run the script again.  
For each image folder in the "Artists" folder, an organised .pur file containing these images will be created in the "Purs" folder.  
Example:
```
Artists/
    Artist1/
        Image1.jpg
        Image2.jpg
        Image3.png
    Artist2/
        Image1.jpg
        Image2.jpeg
        Image3.jpeg
Purs/
    Artist1.pur
    Artist2.pur
```

You may also pass arguments to specify the input folder and output folder, for example `python pureref_gen_script.py input output`  

If your input folder does not have subfolders with images, the script will try to use images in the input folder directly.  
Already existing .pur files will be skipped, so delete them if you want to regenerate them. Empty files will not be generated.  

### Content
`pureref_gen_script.py` script to convert all folders (default Artists/) to .pur files (default Purs/)  
`pureref_gen.py` module with a function to generate an organised PureRef .pur file from a folder of images  
`purformat.py` module with a reader and writer for PureRef files, can be used to write your own converter 

### About
I was inspired to create this after making an Artstation webscraper: https://github.com/FyorUU/Artstation-webscraper  
Because I like collecting huge amounts of reference which I wanted to save time on, and wondered if the next step (putting the images in PureRef files) could be automated too.
