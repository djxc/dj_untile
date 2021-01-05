const gdal = require('gdal');
const { createCanvas, Image, ImageData } = require('canvas')

const TILE_SIZE = 256;
/**
 * **实时切片**  
 * 1、根据空间索引，利用gdal获取指定范围内的矩阵
 * 2、通过canvas将矩阵生成base64图像形式
 */
function readIMG2imgURL(rx, ry, rxsize, rysize, wxsize, wysize, wx, wy) {
    let dataset = gdal.open('./10.tif')
    let bands = dataset.bands
    let maxSize = rxsize > rysize ? rxsize : rysize
    var n = rxsize * rysize;

    const canvas = createCanvas(TILE_SIZE, TILE_SIZE)
    var ctx = canvas.getContext("2d");

    // 用时35ms
    let bandsData = []
    bands.forEach((band, i) => {
        //read data into the existing array
        var data = new Uint8Array(new ArrayBuffer(n));
        band.pixels.read(rx, ry, rxsize, rysize, data);
        bandsData.push(data)
    })
    let allData = []
    // 计算缩放比例
    let rxsizeScale = rxsize / TILE_SIZE
    let rysizeScale = rysize / TILE_SIZE
    let j = 0

    let index = 0
    for (j = 0; j < TILE_SIZE * TILE_SIZE; j++) {
        index = parseInt(rysizeScale * parseInt(j / TILE_SIZE))
        let j_ = parseInt(parseInt(j % TILE_SIZE) * rxsizeScale + index * rxsize)
        // rxsize为一行
        let band1Value = bandsData[0][j_]
        let band2Value = bandsData[1][j_]
        let band3Value = bandsData[2][j_]
        let band4Value = 255
        allData.push(band1Value)
        allData.push(band2Value)
        allData.push(band3Value)
        allData.push(band4Value)
    }
    let uint8Array = Uint8ClampedArray.from(allData)
    let imgData = new ImageData(uint8Array, TILE_SIZE, TILE_SIZE)
    if (wy !== 0 || wx !== 0) {
        ctx.putImageData(imgData, Math.round(wx / 13.47), Math.round(wy / 13.47), 0, 0, TILE_SIZE, TILE_SIZE);
    } else {
        ctx.putImageData(imgData, 0, 0, 0, 0, TILE_SIZE, TILE_SIZE);
    }
    let imgUrl = canvas.toDataURL();
    return imgUrl
}

/**
 * **没有影像数据的图片**
 */
function noIMGTileData() {
    let size = 256
    var n = size * size;
    let w = size, h = size;
    const canvas = createCanvas(w, h)
    var ctx = canvas.getContext("2d");
    // const imgData = ctx.createImageData(w, h);
    var str = "noData";
    ctx.fillStyle = "rgba(100, 100, 100, 0.2)"
    ctx.strokeStyle = "rgba(100, 10, 10, 0.6)"
    ctx.strokeRect(0, 0, canvas.width, canvas.height);
    // ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "red"
    //文字大小
    ctx.font = "20px sans-serif";
    //文字水平居中
    ctx.textAlign = "center";
    //字符str 在画布位置水平居中
    ctx.fillText(str, 128, 128);
    let imgUrl = canvas.toDataURL();
    return imgUrl
}

module.exports = {
    readIMG2imgURL,
    noIMGTileData
}