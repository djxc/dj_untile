/**
 * **在线切片**  
 * 1、读取tiff影像,然后根据请求的xyz进行切片，将影像切片的图片流传给前端
 */
var fs = require('fs');
var express = require('express');
var gdal = require('gdal');
var router = express.Router();

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
    console.log(content);
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
  console.log(req);
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
  let dataset = gdal.open('./japan_origin.tif')
  let bands = dataset.bands
  // bands.forEach((band, i) => {
  //   console.log(band, i);
  // })
  let band1 = bands.get(1)
  var n = 16 * 16;
  var data = new Float32Array(new ArrayBuffer(n * 4));
  //read data into the existing array
  band1.pixels.read(0, 0, 16, 16, data);
  let data_ = toBuffer(data)
  console.log(data_);
  // console.log("number of bands: " + dataset.bands.count());
  // console.log("width: " + dataset.rasterSize.x);
  // console.log("height: " + dataset.rasterSize.y);
  // console.log("geotransform: " + dataset.geoTransform);
  // console.log("srs: " + (dataset.srs ? dataset.srs.toWKT() : 'null'));
  res.send(data_)
})

router.get('/test/:x/:y/:z', (req, res, next) => {
  let x = req.params.x
  let y = req.params.y
  let z = req.params.z.split('.')[0]
  console.log(x, y, z);
  let res_ = getIMG(res)
  res_.send()
})

module.exports = router