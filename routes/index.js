var express = require('express');
var getAllOrders = require('../src/controller/orderController');
const createFileAndWrite = require('../src/util/operateFile');
var router = express.Router();


/* GET home page. */
router.get('/', function (req, res, next) {
  let max = max_num(10, 20);
  console.log(max);
  res.render('index', { title: 'Express' });
});

router.get('/orders', (req, res, next) => {
  getAllOrders((result) => {
    createFileAndWrite(result)
  })
  res.send('query orders');
})

module.exports = router;
