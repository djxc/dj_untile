/**
 * **切片空间索引** 
 * 
 */

var dbConnect = require('./connectMongodb')

/**
 * **获取空间索引**
 * @param {function} callback 
 */
var querySpatialIndex = function (callback) {
    var db = dbConnect().db('bhqd')
    db.collection('blog').find().toArray((err, result) => {
        if (err) throw err
        callback(result)
    })
}

module.exports = {
    querySpatialIndex
}