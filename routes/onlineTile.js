/**
 * **在线切片**  
 * 1、读取tiff影像,然后根据请求的xyz进行切片，将影像切片的图片流传给前端
 */
var fs = require('fs');
var express = require('express');
var gdal = require('gdal');
var router = express.Router();
const { createCanvas, Image } = require('canvas')

const {get_tile_index} = require("../src/util/operateFile");
const {readIMG2imgURL} = require("../src/util/gdal_image");

/**
 * **将图像放在响应中返回**
 * @param {*} res 
 */
function getIMG(res) {
  //设置请求的返回头type,content的type类型列表见上面
  res.setHeader("Content-Type", "image/png");
  try {
    //格式必须为 binary 否则会出错
    var content = fs.readFileSync("./test.png", "binary");
    // console.log(content);
    res.writeHead(200, "Ok");
    res.write(content, "binary"); //格式必须为 binary，否则会出错
  } catch (error) {
    console.log(error);
    res.writeHead(500, "error");
  } finally {
    return res
  }
}

/* GET home page. */
router.get('/', function (req, res, next) {
  // console.log(req);
  get_tile_index(19, 262143, 262140, (dd)=>{
    console.log("----", dd);
  });
  console.log("-=-=-=-=");
  let res_ = getIMG(res)
  res_.send()
});

function toBuffer(ab) {
  var buf = new Buffer.from(ab);
  var view = new Uint8Array(ab);
  for (var i = 0; i < buf.length; ++i) {
    buf[i] = view[i];
  }
  return buf;
}


router.get('/gdal', (req, res, next) => {
  try {
    let dataset = gdal.open('./10.tif')
    let bands = dataset.bands
    let size = 256
    var n = size * size;
    let w = size, h = size;

    const canvas = createCanvas(w, h)
    var ctx = canvas.getContext("2d");
    const imgData = ctx.createImageData(w, h);
    // 用时35ms
    let bandsData = []
    bands.forEach((band, i) => {
      //read data into the existing array
      var data = new Uint8Array(new ArrayBuffer(n));
      band.pixels.read(500, 1000, size, size, data);
      bandsData.push(data)
    })
    let allData = []
    for (let i = 0; i < n; i++) {
      let band1Value = bandsData[0][i]
      let band2Value = bandsData[1][i]
      let band3Value = bandsData[2][i]
      let band4Value = 255
      allData.push(band1Value)
      allData.push(band2Value)
      allData.push(band3Value)
      allData.push(band4Value)
    }
    let uint8Array = Uint8Array.from(allData)

    imgData.data.set(uint8Array);
    ctx.putImageData(imgData, 0, 0);
    let imgUrl = canvas.toDataURL();
    // console.log("number of bands: " + dataset.bands.count());
    // console.log("width: " + dataset.rasterSize.x);
    // console.log("height: " + dataset.rasterSize.y);
    // console.log("geotransform: " + dataset.geoTransform);
    // console.log("srs: " + (dataset.srs ? dataset.srs.toWKT() : 'null'));
    // res.send(imgUrl)
    res.send(imgUrl)

  } catch (e) {
    console.log(e);
  } finally {

  }

})


/**
 * **无切片**  
 * 1、通过gdal读取tif文件，获取每个波段的数据
 * 2、利用canvas在服务器端生成图像，转换为字符串，返回客户端
 * 3、根据请求的xyz找到该切片的位置信息
 */
router.get('/test/:x/:y/:z', (req, res, next) => {
  let x = req.params.x
  let y = req.params.y
  let z = req.params.z.split('.')[0]
  console.log(x, y, z);
  try {
    let imgUrl = readIMG2imgURL()  
    res.send(imgUrl)
  } catch (e) {
    console.log(e);
    res.send('dj')
  }
})

module.exports = router