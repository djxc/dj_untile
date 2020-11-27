let mysql = require("mysql");

/**
 * **单例模式创建数据库连接**
 */
var mySQLConnect = (function () {
    var connect
    return function () {
        if (connect) {
            return connect
        } else {
            return connect = mysql.createConnection({
                // host: '47.105.69.6',
                host: 'localhost',
                user: 'root',
                password: '123dj321',
                database: 'eladmin'
            })
        }
    }
})()

module.exports = mySQLConnect