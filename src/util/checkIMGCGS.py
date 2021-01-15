import gdal
from osgeo import osr

def checkGCS(projection):
    '''检查地理坐标系
        1、如果地理坐标为wgs84则返回true，否则返回false
    '''
    in_srs = osr.SpatialReference()
    in_srs.ImportFromWkt(projection)
    gcs = in_srs.GetAttrValue("GEOGCS")
    pcs = in_srs.GetAttrValue("PROJCS")

    isWGS84 = False
    if gcs == "WGS 84":
        isWGS84 = True

    if isWGS84 == False:
        if projection == "":
            print("no geo coord sys")
        else:
            print(projection)
    else:
        try:
            if pcs.find("UTM") == -1:
                if projection == "":
                    print("no project")
                else:
                    print(projection)
        except:
            pass


    return isWGS84

def readIMG(imgPath):
    """用GDAL读影像
        1、获取影像基本信息，包括行列数、坐标、波段以及仿射矩阵等。
        @param imgPath 要读取的影像文件
    """
    dataset = gdal.Open(imgPath, gdal.GA_ReadOnly)

    im_width = dataset.RasterXSize                          # 栅格矩阵的列数
    im_height = dataset.RasterYSize                         # 栅格矩阵的行数
    bands = dataset.RasterCount                             # 获取波段数

    # 仿射矩阵，0，3表示左上角的坐标，1，5指示像元大小
    im_geotrans = dataset.GetGeoTransform()
    im_proj = dataset.GetProjection()                       # 地图投影信息
    return im_width, im_height, im_proj, im_geotrans, dataset, bands

if __name__ == "__main__":
    imgPath = "/document/2020/usa_2-20181218_L20_1w.tif"
    im_width, im_height, im_proj, im_geotrans, dataset, bands = readIMG(imgPath)
    checkGCS(im_proj)