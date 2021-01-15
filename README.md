# untile map server
In order to build xyz style raster map server without tiling, which spends too long time. I write nodejs server using express, so that I can public a image in seconds and change rgb channels, and so on.
![avatar](./test.gif)

* 1、To create image response, I use [gdal2tiles](https://gdal.org/programs/gdal2tiles.html)(util/gdal2tiles_spatialIndex.py) to generate spatial index.And I use [node-gdal](https://github.com/naturalatlas/node-gdal) to read tif images, and use node-canvas to create small images. Finally, response the small images.
* 2、I use openlayers to display map in electron，like this：
```javascript
    this.map = new Map({
    target: 'map',
    layers: [
        new TileLayer({
        source: new XYZ({
            url: 'http://localhost:3001/onlineTile/test/{z}/{x}/{-y}.png',
            tileLoadFunction: (imageTile, src) => {
            fetch(src, {
                method: 'GET'
            })
                .then((res) => res.text())
                .then((data) => {
                imageTile.getImage().src = data
                })
                .catch((error) => {
                console.log(error)
                })
            }
        })
        })
    ],
    view: new View({
        // projection: 'EPSG:4326',
        center: [0, 0],
        zoom: 19
    })
    })
```
# Getting Started
- 1、git clone https://github.com/djxc/dj_untile.git
- 2、cd dj_untile & npm i
- 3、start server `npm run dev`
- 4、create spatial index file `python gdal2tiles_spatialIndex.py input.tif output_folder`
- 5、display use mapbox、openlayers。

## express项目
* 1、通过express手脚架创建express项目，`express --view=ejs app`；然后通过npm start运行该项目
* 2、项目结构，1)public中存储静态资源文件；2)route存储控制器(路由)；3)views中存储页面模板；4)dao存储数据库的基本操作；5)util存储工具函数
* 3、为了进行代码热更新，需要全局安装node-dev,然后在package.json中添加`"dev":"node-dev ./bin/www"`，启动运行`npm run dev`即可进行热更新。

- 1、c++项目下执行./configure对项目生成路径进行配置，项目生成的可执行文件或连接库存放的路径，等信息。
- 2、安装完程序可以在终端使用命令，也可以利用语言进行调用，这里采用c++为例：在test_proj.cpp中引用程序的头文件，`g++ test_proj.cpp -o test_proj -L /usr/local/lib/ -lproj`-L为告诉c++编译器到该路径下找依赖文件，-lproj则为依赖该库；g++使用gdal`g++ test_gdal.cpp -L /usr/bin -lgdal`
- 3、nodejs调用c++,通过node-gyp将其他语言程序编译为可供nodejs调用。
  - 3.1、用c++编写完程序，需要在头部引用`<node.h>`，让c++找到v8。由于不同版本的node采用的v8引擎有些变化，因此可以采用`nan(Native Abstractions for Node)`处理版本之间的差异，需要在node项目中安装nan`npm install --save nan`，然后在c++程序中`<nan.h>`替换`<node.h>`,还需要在`binding.gyp`文件中添加
  ```javascript
    "include_dirs" : [ 
        "<!(node -e \"require('nan')\")"
    ]
  ```
  - 3.2、编写配置文件`binding.gyp`，
  - 3.4、采用以下方式生成nodejs可调用的程序`node-gyp configure; node-gyp build`,build命令会生成一个build文件夹其中包括编译好的二进制代码