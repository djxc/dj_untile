## express项目
* 1、通过express手脚架创建express项目，`express --view=ejs app`；然后通过npm start运行该项目
* 2、项目结构，1)public中存储静态资源文件；2)route存储控制器(路由)；3)views中存储页面模板；4)dao存储数据库的基本操作；5)util存储工具函数
* 3、为了进行代码热更新，需要全局安装node-dev,然后在package.json中添加`"dev":"node-dev ./bin/www"`，启动运行`npm run dev`即可进行热更新。