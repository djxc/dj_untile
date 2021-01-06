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