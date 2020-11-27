var express = require('express');
var router = express.Router();
var ObjectId = require('mongodb').ObjectId ;
var { queryBlogs, changeBlog } = require('../dao/blog_dao')

/* GET users listing. */
router.get('/', function (req, res, next) {
  res.send('respond with a resource');
});

router.get('/dj', function (req, res, next) {
  queryBlogs(result => {
    res.send(result);
  })
});

router.post('/save_article', (req, res, next) => {
  let article = req.body
  console.log("req_____________", article)
  changeBlog(ObjectId(article.id), article.content, (result) => {
    // console.log(result)
    res.send("djxc")
  })
})



module.exports = router;
