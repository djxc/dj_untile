const gdal = require('gdal');
const { createCanvas, Image } = require('canvas')

/**
 *  if rxsize != 0 and rysize != 0 and wxsize != 0 and wysize != 0:
        data = ds.ReadRaster(rx, ry, rxsize, rysize, wxsize, wysize,
                             band_list=list(range(1, dataBandsCount + 1)))
        alpha = alphaband.ReadRaster(rx, ry, rxsize, rysize, wxsize, wysize)

    # The tile in memory is a transparent file by default. Write pixel values into it if
    # any
    if data:
        if tilesize == querysize:
            # Use the ReadRaster result directly in tiles ('nearest neighbour' query)
            dstile.WriteRaster(wx, wy, wxsize, wysize, data,
                               band_list=list(range(1, dataBandsCount + 1)))
            dstile.WriteRaster(wx, wy, wxsize, wysize,
                               alpha, band_list=[tilebands])
    rx, ry, rxsize, rysize, wxsize, wysize, wx, wy

 */
function readIMG2imgURL(rx, ry, rxsize, rysize, wxsize, wysize, wx, wy) {
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
        band.pixels.read(rx, ry, rxsize, rysize, data);
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
    // res.send(imgUrl)
    return imgUrl
}

module.exports = {
    readIMG2imgURL
}