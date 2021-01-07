const gdal = require('gdal');
const { createCanvas, Image, ImageData } = require('canvas')

const TILE_SIZE = 256;
/**
 * **实时切片**  
 * 1、根据空间索引，利用gdal获取指定范围内的矩阵
 * 2、通过canvas将矩阵生成base64图像形式
 * 3、wx与wy为图像的位置与左上角的偏移量；wxsize与wysize则为图像的长宽比例
 * 
 * 1、单一客户访问情况下nginx响应为5-10ms；本服务为50-100ms。
 * 2、node服务处理慢的原因可能为：
 *  1) 读取文件获取空间索引。解决方案：将空间索引放在数据库中存储，查询速度块
 *  2) gdal处理图像，重采样生成新的图像
 */
function readIMG2imgURL(rx, ry, rxsize, rysize, wxsize, wysize, wx, wy) {
    let dataset = gdal.open('./10.tif')
    let bands = dataset.bands
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
    let rxsizeScale = rxsize / (TILE_SIZE * (wxsize / 1024))
    let rysizeScale = rysize / (TILE_SIZE * (wysize / 1024))
    let j = 0
    // 如果wxsize 小于 wx则在右侧，否则在左侧；如果wysize 小于 wy在下侧，否则在上侧
    let index = 0 // 在原矩阵中的行数
    for (j = 0; j < TILE_SIZE * TILE_SIZE; j++) {
        // index为原始矩阵的行数
        index = parseInt(rysizeScale * parseInt(j / TILE_SIZE))
        // col_index为原始矩阵的列数,如果col_index大于rxsize则将其后的像素设为透明
        let col_index = parseInt(j % (TILE_SIZE)) * rxsizeScale
        // j_为当前像素在原始数组的位置
        let j_ = parseInt(col_index + index * rxsize)

        // 如果bandsData不存在则将其设为透明，否则不透明
        let band4Value = bandsData[0][j_] ? 255 : 0
        if(col_index > rxsize) {
            band4Value = 0;
        }
        let band1Value = bandsData[0][j_] ? bandsData[0][j_] : 255
        let band2Value = bandsData[1][j_] ? bandsData[1][j_] : 255
        let band3Value = bandsData[2][j_] ? bandsData[2][j_] : 255
        allData.push(band1Value)
        allData.push(band2Value)
        allData.push(band3Value)
        allData.push(band4Value)

    }
    let uint8Array = Uint8ClampedArray.from(allData)
    let imgData = new ImageData(uint8Array, TILE_SIZE, TILE_SIZE)
    ctx.putImageData(imgData, Math.round(wx / 1024 * 256), Math.round(wy / 1024 * 256), 0, 0, TILE_SIZE, TILE_SIZE);
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