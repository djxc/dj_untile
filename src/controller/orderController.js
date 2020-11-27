var mySQLConnect = require('../../dao/connectMySQL')


function getAllOrders(callback) {
    let connection = mySQLConnect()
    connection.connect();

    connection.query('SELECT username, nick_name, sex, phone from user;',
        function (error, results, fields) {
            if (error) throw error;
            console.log('The solution is: ', results[0]);
            callback(results)
        });
}

module.exports = getAllOrders