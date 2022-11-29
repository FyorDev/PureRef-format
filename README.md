# PureRef-library  
Reverse engineered the .pur file format (PureRef 1.11.1) so you can automatically generate PureRef files or use this library to convert from/to any other file format.

Cool demonstration in purerefGenerator.py which generates a neatly organised PureRef file from a folder of images.  
Run purerefArtistGenerator.py to create files from all ./Artists image folders to ./Purs PureRef files  

I made this after creating an Artstation webscraper: https://github.com/FyorUU/Artstation-webscraper  
Because I wanted to save time gathering tons of reference, and wondered if the next step could be automated too.

TODO:
- Refactor lots, and comment  
  - Explain in comments how img address - transform ID are linked  
- Better documentation  
- Add image source instead of making everything BruteForceLoaded, handle chinese characters  
- Write file format specification  
- Use crop points to generate a circle, for fun and demonstration  
- Convert to another file format to give an example? XML?  
