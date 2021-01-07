var MongodbClient = require('mongodb').MongoClient

var dbURL = "mongodb://userName:password@xx.xx.xx.xx:27017"
var option = {
    reconnectTries: 3,
    auto_reconnect: true,
    poolSize : 40,
    connectTimeoutMS: 500,
    useNewUrlParser: true
};

/**
 * **采用数据库连接池连接数据库**  
 * 1、返回数据库连接
 */
function connectDB(callback) {
    MongodbClient.connect(dbURL, option, (err, db) => {
        if (err) throw err
        callback(db)       
    })
}

/**
 * **单例模式创建数据库连接**
 */
var dbConnect = (function () { 
    var connect
    return function () {
        if (connect) {
            return connect
        } else {
            connectDB((db) => {
                connect = db
                return connect
            })
        }
    }
})()

module.exports = dbConnect
