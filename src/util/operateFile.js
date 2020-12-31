/**
 * @FileDecription nodejs读取文件
 * 1、为处理gbk编码需要安装 iconv-lite第三方库
 * @Author small dj
 * @Date 2020-11-27
 * 
 */
const fs = require('fs');
const readline = require('readline');
let iconv = require('iconv-lite')

function createFileAndWrite(result_data) {
    let file = "/document/2020/test_djxc.csv";
    let data = ""
    for (let i in result_data) {
        let userInfo = result_data[i]
        data += userInfo.username + ', ' + userInfo.nick_name + ', ' + userInfo.sex + ', ' + userInfo.phone
        data += '\n'
    }
    let str_ = iconv.encode(data, 'gbk');
    fs.writeFile(file, str_, err => {
        if (err) {

        } else {
            console.log("写入成功");
        }
    })
}

/***********************************************************
 * **获取切片的空间索引**  
 * 1、如果文件内容过大则不能一次将所有内容读入文件中，因此需要按行读取  
 * 2、通过等级、坐标位置，获取该切片的空间索引
 * @param z zoom等级
 * @param x x坐标位置
 * @param y y坐标位置
 ***********************************************************/
async function get_tile_index(z, x, y, callback) {
    z = parseInt(z)
    x = parseInt(x)
    y = parseInt(y)
    console.log(z, x, y);
    const readInterface = readline.createInterface({
      input: fs.createReadStream("/home/djxc/demo.json"),
      output: false,
      console: false
    });
    readInterface.on('line', function (line) {
      line = line.trim()
      // console.log(line, line.length);
      try {
        if (line.length > 1) {
          let tileInfo = JSON.parse(line.slice(0, line.length - 1))
          let { tz, tx, ty, rx, ry, rxsize, rysize, wxsize, wysize, wx, wy } = tileInfo
          if (tz === z && tx === x && ty === y) {
            console.log(tz, tx, ty, rx, ry, rxsize, rysize, wxsize, wysize, wx, wy);
            callback(tileInfo)
            readInterface.close()
            // return tileInfo
          }
        }
      } finally {
        readInterface.close()
      }
    });
    console.log("djxc");
    readInterface.on("close", ()=>{
      console.log("dddd");
    })
  }

module.exports ={
    createFileAndWrite,
    get_tile_index
} 