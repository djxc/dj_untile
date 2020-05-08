var dbConnect = require('./connectMongodb')

/**
 * **获取博客**
 * @param {function} callback 
 */
var queryBlogs = function (callback) {
    var db = dbConnect().db('bhqd')
    db.collection('blog').find().toArray((err, result) => {
        if (err) throw err
        callback(result)
    })
}

/**
 * **修改博客**
 * @param {string} articleID 文章的id
 * @param {string} content 文章内容
 * @param {function} callback 回调函数
 */
var changeBlog = function (articleID, content, callback) {
    var db = dbConnect().db('bhqd')
    // db.collection('blog').update({})
    db.collection('blog').updateOne({ _id: articleID }
        , { $set: { 'content': content } }, function (err, result) {
            // assert.equal(err, null);
            // assert.equal(1, result.result.n);
            // console.timeEnd('start');
            // console.log("Updated the document with the field a equal to 2");
            if (err) throw err
            callback(result);
        });
}

module.exports = { queryBlogs, changeBlog }