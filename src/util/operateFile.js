/**
 * @FileDecription nodejs读取文件
 * 1、为处理gbk编码需要安装 iconv-lite第三方库
 * @Author small dj
 * @Date 2020-11-27
 * 
 */

let fs = require('fs');
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

module.exports = createFileAndWrite