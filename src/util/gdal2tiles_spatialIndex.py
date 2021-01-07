# 利用gdal2tiles工具生成空间索引
# #

# -*- coding: utf-8 -*-

# ******************************************************************************
#  $Id$
#
# Project:  Google Summer of Code 2007, 2008 (http://code.google.com/soc/)
# Support:  BRGM (http://www.brgm.fr)
# Purpose:  Convert a raster into TMS (Tile Map Service) tiles in a directory.
#           - generate Google Earth metadata (KML SuperOverlay)
#           - generate simple HTML viewer based on Google Maps and OpenLayers
#           - support of global tiles (Spherical Mercator) for compatibility
#               with interactive web maps a la Google Maps
# Author:   Klokan Petr Pridal, klokan at klokan dot cz
# Web:      http://www.klokan.cz/projects/gdal2tiles/
# GUI:      http://www.maptiler.org/
#
###############################################################################
# Copyright (c) 2008, Klokan Petr Pridal
# Copyright (c) 2010-2013, Even Rouault <even dot rouault at mines-paris dot org>
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
# ******************************************************************************

from __future__ import print_function, division

import math
import os
import tempfile
import shutil
import sys
from uuid import uuid4
from xml.etree import ElementTree
from bson.json_util import dumps

try:
    # try to use billiard because it seems to works with Celery
    # https://github.com/celery/celery/issues/1709
    from billiard import Pipe, Pool, Process, Manager
except ImportError:
    from multiprocessing import Pipe, Pool, Process, Manager

from osgeo import gdal
from osgeo import osr

try:
    from PIL import Image
    import numpy
    import osgeo.gdal_array as gdalarray
except Exception:
    # 'antialias' resampling is not available
    pass

resampling_list = ('average', 'near', 'bilinear', 'cubic',
                   'cubicspline', 'lanczos', 'antialias')
profile_list = ('mercator', 'geodetic', 'raster')
webviewer_list = ('all', 'google', 'openlayers', 'leaflet', 'none')

# =============================================================================
# =============================================================================
# =============================================================================

__doc__globalmaptiles = """
globalmaptiles.py

Global Map Tiles as defined in Tile Map Service (TMS) Profiles
==============================================================

Functions necessary for generation of global tiles used on the web.
It contains classes implementing coordinate conversions for:

  - GlobalMercator (based on EPSG:3857)
       for Google Maps, Yahoo Maps, Bing Maps compatible tiles
  - GlobalGeodetic (based on EPSG:4326)
       for OpenLayers Base Map and Google Earth compatible tiles

More info at:

http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification
http://wiki.osgeo.org/wiki/WMS_Tiling_Client_Recommendation
http://msdn.microsoft.com/en-us/library/bb259689.aspx
http://code.google.com/apis/maps/documentation/overlays.html#Google_Maps_Coordinates

Created by Klokan Petr Pridal on 2008-07-03.
Google Summer of Code 2008, project GDAL2Tiles for OSGEO.

In case you use this class in your product, translate it to another language
or find it useful for your project please let me know.
My email: klokan at klokan dot cz.
I would like to know where it was used.

Class is available under the open-source GDAL license (www.gdal.org).
"""

MAXZOOMLEVEL = 32
# 默认切片配置信息
DEFAULT_GDAL2TILES_OPTIONS = {
    'verbose': False,
    'title': '',
    'profile': 'mercator',
    'url': '',
    'resampling': 'average',
    's_srs': None,
    'zoom': None,
    'resume': False,
    'srcnodata': None,
    'tmscompatible': None,
    'quiet': False,
    'kml': False,
    'webviewer': 'all',
    'copyright': '',
    'googlekey': 'INSERT_YOUR_KEY_HERE',
    'bingkey': 'INSERT_YOUR_KEY_HERE',
    'nb_processes': 1
}

class Zoomify(object):
    """
    Tiles compatible with the Zoomify viewer
    ----------------------------------------
    """

    def __init__(self, width, height, tilesize=256, tileformat='jpg'):
        """Initialization of the Zoomify tile tree"""

        self.tilesize = tilesize
        self.tileformat = tileformat
        imagesize = (width, height)
        tiles = (math.ceil(width / tilesize), math.ceil(height / tilesize))

        # Size (in tiles) for each tier of pyramid.
        self.tierSizeInTiles = []
        self.tierSizeInTiles.append(tiles)

        # Image size in pixels for each pyramid tierself
        self.tierImageSize = []
        self.tierImageSize.append(imagesize)

        while (imagesize[0] > tilesize or imagesize[1] > tilesize):
            imagesize = (math.floor(
                imagesize[0] / 2), math.floor(imagesize[1] / 2))
            tiles = (math.ceil(imagesize[0] / tilesize),
                     math.ceil(imagesize[1] / tilesize))
            self.tierSizeInTiles.append(tiles)
            self.tierImageSize.append(imagesize)

        self.tierSizeInTiles.reverse()
        self.tierImageSize.reverse()

        # Depth of the Zoomify pyramid, number of tiers (zoom levels)
        self.numberOfTiers = len(self.tierSizeInTiles)

        # Number of tiles up to the given tier of pyramid.
        self.tileCountUpToTier = []
        self.tileCountUpToTier[0] = 0
        for i in range(1, self.numberOfTiers + 1):
            self.tileCountUpToTier.append(
                self.tierSizeInTiles[i - 1][0] * self.tierSizeInTiles[i - 1][1] +
                self.tileCountUpToTier[i - 1]
            )

    def tilefilename(self, x, y, z):
        """Returns filename for tile with given coordinates"""

        tileIndex = x + y * \
            self.tierSizeInTiles[z][0] + self.tileCountUpToTier[z]
        return os.path.join("TileGroup%.0f" % math.floor(tileIndex / 256),
                            "%s-%s-%s.%s" % (z, x, y, self.tileformat))

def exit_with_error(message, details=""):
    # Message printing and exit code kept from the way it worked using the OptionParser (in case
    # someone parses the error output)
    sys.stderr.write("Usage: gdal2tiles.py [options] input_file [output]\n\n")
    sys.stderr.write("gdal2tiles.py: error: %s\n" % message)
    if details:
        sys.stderr.write("\n\n%s\n" % details)

    sys.exit(2)

def scale_query_to_tile(dsquery, dstile, tiledriver, options, tilefilename=''):
    """Scales down query dataset to the tile dataset"""

    querysize = dsquery.RasterXSize
    tilesize = dstile.RasterXSize
    tilebands = dstile.RasterCount

    if options.resampling == 'average':

        # Function: gdal.RegenerateOverview()
        for i in range(1, tilebands + 1):
            # Black border around NODATA
            res = gdal.RegenerateOverview(dsquery.GetRasterBand(i), dstile.GetRasterBand(i),
                                          'average')
            if res != 0:
                exit_with_error("RegenerateOverview() failed on %s, error %d" % (
                    tilefilename, res))

    elif options.resampling == 'antialias':

        # Scaling by PIL (Python Imaging Library) - improved Lanczos
        array = numpy.zeros((querysize, querysize, tilebands), numpy.uint8)
        for i in range(tilebands):
            array[:, :, i] = gdalarray.BandReadAsArray(dsquery.GetRasterBand(i + 1),
                                                       0, 0, querysize, querysize)
        im = Image.fromarray(array, 'RGBA')     # Always four bands
        im1 = im.resize((tilesize, tilesize), Image.ANTIALIAS)
        if os.path.exists(tilefilename):
            im0 = Image.open(tilefilename)
            im1 = Image.composite(im1, im0, im1)
        im1.save(tilefilename, tiledriver)

    else:

        if options.resampling == 'near':
            gdal_resampling = gdal.GRA_NearestNeighbour

        elif options.resampling == 'bilinear':
            gdal_resampling = gdal.GRA_Bilinear

        elif options.resampling == 'cubic':
            gdal_resampling = gdal.GRA_Cubic

        elif options.resampling == 'cubicspline':
            gdal_resampling = gdal.GRA_CubicSpline

        elif options.resampling == 'lanczos':
            gdal_resampling = gdal.GRA_Lanczos

        # Other algorithms are implemented by gdal.ReprojectImage().
        dsquery.SetGeoTransform((0.0, tilesize / float(querysize), 0.0, 0.0, 0.0,
                                 tilesize / float(querysize)))
        dstile.SetGeoTransform((0.0, 1.0, 0.0, 0.0, 0.0, 1.0))

        res = gdal.ReprojectImage(dsquery, dstile, None, None, gdal_resampling)
        if res != 0:
            exit_with_error(
                "ReprojectImage() failed on %s, error %d" % (tilefilename, res))

def process_options(input_file, output_folder, options={}):
    '''切片进程的参数
        1、首先获取默认参数，
        2、然后通过传入的参数更新已有的参数
        3、最后通过`options_post_processing`方法处理参数
    '''
    _options = DEFAULT_GDAL2TILES_OPTIONS.copy()
    _options.update(options)
    # options = AttrDict(_options)
    options = options_post_processing(options, input_file, output_folder)
    return options

def options_post_processing(options, input_file, output_folder):
    """
        检查切片配置信息，如果不符合要求直接退出程序
    """
    if not options.title:
        options.title = os.path.basename(input_file)

    if options.url and not options.url.endswith('/'):
        options.url += '/'
    if options.url:
        out_path = output_folder
        if out_path.endswith("/"):
            out_path = out_path[:-1]
        options.url += os.path.basename(out_path) + '/'

    if isinstance(options.zoom, (list, tuple)) and len(options.zoom) < 2:
        raise ValueError('Invalid zoom value')

    # Supported options
    if options.resampling == 'average':
        try:
            if gdal.RegenerateOverview:
                pass
        except Exception:
            exit_with_error("'average' resampling algorithm is not available.",
                            "Please use -r 'near' argument or upgrade to newer version of GDAL.")

    elif options.resampling == 'antialias':
        try:
            if numpy:     # pylint:disable=W0125
                pass
        except Exception:
            exit_with_error("'antialias' resampling algorithm is not available.",
                            "Install PIL (Python Imaging Library) and numpy.")

    try:
        os.path.basename(input_file).encode('ascii')
    except UnicodeEncodeError:
        full_ascii = False
    else:
        full_ascii = True

    # LC_CTYPE check
    if not full_ascii and 'UTF-8' not in os.environ.get("LC_CTYPE", ""):
        if not options.quiet:
            print("\nWARNING: "
                  "You are running gdal2tiles.py with a LC_CTYPE environment variable that is "
                  "not UTF-8 compatible, and your input file contains non-ascii characters. "
                  "The generated sample googlemaps, openlayers or "
                  "leaflet files might contain some invalid characters as a result\n")

    # Output the results
    if options.verbose:
        print("Options:", options)
        print("Input:", input_file)
        print("Output:", output_folder)
        print("Cache: %s MB" % (gdal.GetCacheMax() / 1024 / 1024))
        print('')

    return options

def nb_data_bands(dataset):
    """
    Return the number of data (non-alpha) bands of a gdal dataset
    """
    alphaband = dataset.GetRasterBand(1).GetMaskBand()
    if ((alphaband.GetMaskFlags() & gdal.GMF_ALPHA) or
            dataset.RasterCount == 4 or
            dataset.RasterCount == 2):
        return dataset.RasterCount - 1
    else:
        return dataset.RasterCount

def update_alpha_value_for_non_alpha_inputs(warped_vrt_dataset, options=None):
    """
    Handles dataset with 1 or 3 bands, i.e. without alpha channel, in the case the nodata value has
    not been forced by options
    """
    if warped_vrt_dataset.RasterCount in [1, 3]:
        tempfilename = gettempfilename('-gdal2tiles.vrt')
        warped_vrt_dataset.GetDriver().CreateCopy(tempfilename, warped_vrt_dataset)
        with open(tempfilename) as f:
            orig_data = f.read()
        alpha_data = add_alpha_band_to_string_vrt(orig_data)
        with open(tempfilename, 'w') as f:
            f.write(alpha_data)

        warped_vrt_dataset = gdal.Open(tempfilename)
        os.unlink(tempfilename)

        if options and options.verbose:
            print("Modified -dstalpha warping result saved into 'tiles1.vrt'")
            # TODO: gbataille - test replacing that with a gdal write of the dataset (more
            # accurately what's used, even if should be the same
            with open("tiles1.vrt", "w") as f:
                f.write(alpha_data)

    return warped_vrt_dataset

def update_no_data_values(warped_vrt_dataset, nodata_values, options=None):
    """
    Takes an array of NODATA values and forces them on the WarpedVRT file dataset passed
    """
    # TODO: gbataille - Seems that I forgot tests there
    if nodata_values != []:
        temp_file = gettempfilename('-gdal2tiles.vrt')
        warped_vrt_dataset.GetDriver().CreateCopy(temp_file, warped_vrt_dataset)
        with open(temp_file, 'r') as f:
            vrt_string = f.read()

        vrt_string = add_gdal_warp_options_to_string(
            vrt_string, {"INIT_DEST": "NO_DATA", "UNIFIED_SRC_NODATA": "YES"})

    # TODO: gbataille - check the need for this replacement. Seems to work without
    #         # replace BandMapping tag for NODATA bands....
    #         for i in range(len(nodata_values)):
    #             s = s.replace(
    #                 '<BandMapping src="%i" dst="%i"/>' % ((i+1), (i+1)),
    #                 """
    # <BandMapping src="%i" dst="%i">
    # <SrcNoDataReal>%i</SrcNoDataReal>
    # <SrcNoDataImag>0</SrcNoDataImag>
    # <DstNoDataReal>%i</DstNoDataReal>
    # <DstNoDataImag>0</DstNoDataImag>
    # </BandMapping>
    #                 """ % ((i+1), (i+1), nodata_values[i], nodata_values[i]))

        # save the corrected VRT
        with open(temp_file, 'w') as f:
            f.write(vrt_string)

        corrected_dataset = gdal.Open(temp_file)
        os.unlink(temp_file)

        # set NODATA_VALUE metadata
        corrected_dataset.SetMetadataItem(
            'NODATA_VALUES', ' '.join([str(i) for i in nodata_values]))

        if options and options.verbose:
            print("Modified warping result saved into 'tiles1.vrt'")
            # TODO: gbataille - test replacing that with a gdal write of the dataset (more
            # accurately what's used, even if should be the same
            with open("tiles1.vrt", "w") as f:
                f.write(vrt_string)

        return corrected_dataset

def setup_no_data_values(input_dataset, options):
    """
    Extract the NODATA values from the dataset or use the passed arguments as override if any
    获取nodata的值
    """
    in_nodata = []
    if options.srcnodata:
        nds = list(map(float, options.srcnodata.split(',')))
        if len(nds) < input_dataset.RasterCount:
            in_nodata = (
                nds * input_dataset.RasterCount)[:input_dataset.RasterCount]
        else:
            in_nodata = nds
    else:
        for i in range(1, input_dataset.RasterCount + 1):
            raster_no_data = input_dataset.GetRasterBand(i).GetNoDataValue()
            if raster_no_data is not None:
                in_nodata.append(raster_no_data)

    if options.verbose:
        print("NODATA: %s" % in_nodata)

    return in_nodata


def setup_input_srs(input_dataset, options):
    """
    Determines and returns the Input Spatial Reference System (SRS) as an osr object and as a
    WKT representation

    Uses in priority the one passed in the command line arguments. If None, tries to extract them
    from the input dataset

    设置输入的数据坐标系
    """

    input_srs = None
    input_srs_wkt = None

    if options.s_srs:
        input_srs = osr.SpatialReference()
        input_srs.SetFromUserInput(options.s_srs)
        input_srs_wkt = input_srs.ExportToWkt()
    else:
        input_srs_wkt = input_dataset.GetProjection()
        if not input_srs_wkt and input_dataset.GetGCPCount() != 0:
            input_srs_wkt = input_dataset.GetGCPProjection()
        if input_srs_wkt:
            input_srs = osr.SpatialReference()
            input_srs.ImportFromWkt(input_srs_wkt)

    return input_srs, input_srs_wkt


def setup_output_srs(input_srs, options):
    """
    Setup the desired SRS (based on options)
    
    设置输出的坐标系
    """
    output_srs = osr.SpatialReference()

    if options.profile == 'mercator':
        output_srs.ImportFromEPSG(3857)
    elif options.profile == 'geodetic':
        output_srs.ImportFromEPSG(4326)
    else:
        output_srs = input_srs

    return output_srs


def has_georeference(dataset):
    '''判断数据源是否函数地理坐标'''
    return (dataset.GetGeoTransform() != (0.0, 1.0, 0.0, 0.0, 0.0, 1.0) or
            dataset.GetGCPCount() != 0)


def reproject_dataset(from_dataset, from_srs, to_srs, options=None):
    """
    将输入的数据源修改为期待输出的投影坐标
    Returns the input dataset in the expected "destination" SRS.
    If the dataset is already in the correct SRS, returns it unmodified
    """
    if not from_srs or not to_srs:
        raise GDALError(
            "from and to SRS must be defined to reproject the dataset")

    if (from_srs.ExportToProj4() != to_srs.ExportToProj4()) or (from_dataset.GetGCPCount() != 0):
        to_dataset = gdal.AutoCreateWarpedVRT(from_dataset,
                                              from_srs.ExportToWkt(), to_srs.ExportToWkt())

        if options and options.verbose:
            print(
                "Warping of the raster by AutoCreateWarpedVRT (result saved into 'tiles.vrt')")
            to_dataset.GetDriver().CreateCopy("tiles.vrt", to_dataset)

        return to_dataset
    else:
        return from_dataset


class GlobalMercator(object):
    r"""
    TMS Global Mercator Profile
    生成墨卡托投影的切片
    ---------------------------

    Functions necessary for generation of tiles in Spherical Mercator projection,
    EPSG:3857.

    Such tiles are compatible with Google Maps, Bing Maps, Yahoo Maps,
    UK Ordnance Survey OpenSpace API, ...
    and you can overlay them on top of base maps of those web mapping applications.

    Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

    What coordinate conversions do we need for TMS Global Mercator tiles::

         LatLon      <->       Meters      <->     Pixels    <->       Tile

     WGS84 coordinates   Spherical Mercator  Pixels in pyramid  Tiles in pyramid
         lat/lon            XY in meters     XY pixels Z zoom      XYZ from TMS
        EPSG:4326           EPSG:387
         .----.              ---------               --                TMS
        /      \     <->     |       |     <->     /----/    <->      Google
        \      /             |       |           /--------/          QuadTree
         -----               ---------         /------------/
       KML, public         WebMapService         Web Clients      TileMapService

    What is the coordinate extent of Earth in EPSG:3857?

      [-20037508.342789244, -20037508.342789244, 20037508.342789244, 20037508.342789244]
      Constant 20037508.342789244 comes from the circumference of the Earth in meters,
      which is 40 thousand kilometers, the coordinate origin is in the middle of extent.
      In fact you can calculate the constant as: 2 * math.pi * 6378137 / 2.0
      $ echo 180 85 | gdaltransform -s_srs EPSG:4326 -t_srs EPSG:3857
      Polar areas with abs(latitude) bigger then 85.05112878 are clipped off.

    What are zoom level constants (pixels/meter) for pyramid with EPSG:3857?

      whole region is on top of pyramid (zoom=0) covered by 256x256 pixels tile,
      every lower zoom level resolution is always divided by two
      initialResolution = 20037508.342789244 * 2 / 256 = 156543.03392804062

    What is the difference between TMS and Google Maps/QuadTree tile name convention?

      The tile raster itself is the same (equal extent, projection, pixel size),
      there is just different identification of the same raster tile.
      Tiles in TMS are counted from [0,0] in the bottom-left corner, id is XYZ.
      Google placed the origin [0,0] to the top-left corner, reference is XYZ.
      Microsoft is referencing tiles by a QuadTree name, defined on the website:
      http://msdn2.microsoft.com/en-us/library/bb259689.aspx

    The lat/lon coordinates are using WGS84 datum, yes?

      Yes, all lat/lon we are mentioning should use WGS84 Geodetic Datum.
      Well, the web clients like Google Maps are projecting those coordinates by
      Spherical Mercator, so in fact lat/lon coordinates on sphere are treated as if
      the were on the WGS84 ellipsoid.

      From MSDN documentation:
      To simplify the calculations, we use the spherical form of projection, not
      the ellipsoidal form. Since the projection is used only for map display,
      and not for displaying numeric coordinates, we don't need the extra precision
      of an ellipsoidal projection. The spherical projection causes approximately
      0.33 percent scale distortion in the Y direction, which is not visually
      noticeable.

    How do I create a raster in EPSG:3857 and convert coordinates with PROJ.4?

      You can use standard GIS tools like gdalwarp, cs2cs or gdaltransform.
      All of the tools supports -t_srs 'epsg:3857'.

      For other GIS programs check the exact definition of the projection:
      More info at http://spatialreference.org/ref/user/google-projection/
      The same projection is designated as EPSG:3857. WKT definition is in the
      official EPSG database.

      Proj4 Text:
        +proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0
        +k=1.0 +units=m +nadgrids=@null +no_defs

      Human readable WKT format of EPSG:3857:
         PROJCS["Google Maps Global Mercator",
             GEOGCS["WGS 84",
                 DATUM["WGS_1984",
                     SPHEROID["WGS 84",6378137,298.257223563,
                         AUTHORITY["EPSG","7030"]],
                     AUTHORITY["EPSG","6326"]],
                 PRIMEM["Greenwich",0],
                 UNIT["degree",0.0174532925199433],
                 AUTHORITY["EPSG","4326"]],
             PROJECTION["Mercator_1SP"],
             PARAMETER["central_meridian",0],
             PARAMETER["scale_factor",1],
             PARAMETER["false_easting",0],
             PARAMETER["false_northing",0],
             UNIT["metre",1,
                 AUTHORITY["EPSG","9001"]]]
    """

    def __init__(self, tileSize=256):
        "Initialize the TMS Global Mercator pyramid"
        self.tileSize = tileSize
        self.initialResolution = 2 * math.pi * 6378137 / self.tileSize
        # 156543.03392804062 for tileSize 256 pixels
        self.originShift = 2 * math.pi * 6378137 / 2.0
        # 20037508.342789244

    def LatLonToMeters(self, lat, lon):
        "Converts given lat/lon in WGS84 Datum to XY in Spherical Mercator EPSG:3857"

        mx = lon * self.originShift / 180.0
        my = math.log(math.tan((90 + lat) * math.pi / 360.0)) / \
            (math.pi / 180.0)

        my = my * self.originShift / 180.0
        return mx, my

    def MetersToLatLon(self, mx, my):
        "Converts XY point from Spherical Mercator EPSG:3857 to lat/lon in WGS84 Datum"

        lon = (mx / self.originShift) * 180.0
        lat = (my / self.originShift) * 180.0

        lat = 180 / math.pi * \
            (2 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return lat, lon

    def PixelsToMeters(self, px, py, zoom):
        "Converts pixel coordinates in given zoom level of pyramid to EPSG:3857"

        res = self.Resolution(zoom)
        mx = px * res - self.originShift
        my = py * res - self.originShift
        return mx, my

    def MetersToPixels(self, mx, my, zoom):
        "Converts EPSG:3857 to pyramid pixel coordinates in given zoom level"

        res = self.Resolution(zoom)
        px = (mx + self.originShift) / res
        py = (my + self.originShift) / res
        return px, py

    def PixelsToTile(self, px, py):
        "Returns a tile covering region in given pixel coordinates"

        tx = int(math.ceil(px / float(self.tileSize)) - 1)
        ty = int(math.ceil(py / float(self.tileSize)) - 1)
        return tx, ty

    def PixelsToRaster(self, px, py, zoom):
        "Move the origin of pixel coordinates to top-left corner"

        mapSize = self.tileSize << zoom
        return px, mapSize - py

    def MetersToTile(self, mx, my, zoom):
        "Returns tile for given mercator coordinates"

        px, py = self.MetersToPixels(mx, my, zoom)
        return self.PixelsToTile(px, py)

    def TileBounds(self, tx, ty, zoom):
        """通过给定的切片等级以及xy位置获取墨卡托投影下的范围
        Returns bounds of the given tile in EPSG:3857 coordinates"""

        minx, miny = self.PixelsToMeters(
            tx * self.tileSize, ty * self.tileSize, zoom)
        maxx, maxy = self.PixelsToMeters(
            (tx + 1) * self.tileSize, (ty + 1) * self.tileSize, zoom)
        return (minx, miny, maxx, maxy)

    def TileLatLonBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile in latitude/longitude using WGS84 datum"

        bounds = self.TileBounds(tx, ty, zoom)
        minLat, minLon = self.MetersToLatLon(bounds[0], bounds[1])
        maxLat, maxLon = self.MetersToLatLon(bounds[2], bounds[3])

        return (minLat, minLon, maxLat, maxLon)

    def Resolution(self, zoom):
        "Resolution (meters/pixel) for given zoom level (measured at Equator)"

        # return (2 * math.pi * 6378137) / (self.tileSize * 2**zoom)
        return self.initialResolution / (2**zoom)

    def ZoomForPixelSize(self, pixelSize):
        "Maximal scaledown zoom of the pyramid closest to the pixelSize."

        for i in range(MAXZOOMLEVEL):
            if pixelSize > self.Resolution(i):
                if i != -1:
                    return i - 1
                else:
                    return 0    # We don't want to scale up

    def GoogleTile(self, tx, ty, zoom):
        "Converts TMS tile coordinates to Google Tile coordinates"

        # coordinate origin is moved from bottom-left to top-left corner of the extent
        return tx, (2**zoom - 1) - ty

    def QuadTree(self, tx, ty, zoom):
        "Converts TMS tile coordinates to Microsoft QuadTree"

        quadKey = ""
        ty = (2**zoom - 1) - ty
        for i in range(zoom, 0, -1):
            digit = 0
            mask = 1 << (i - 1)
            if (tx & mask) != 0:
                digit += 1
            if (ty & mask) != 0:
                digit += 2
            quadKey += str(digit)

        return quadKey


class GlobalGeodetic(object):
    r"""
    TMS Global Geodetic Profile
    生成地理坐标的切片
    ---------------------------

    Functions necessary for generation of global tiles in Plate Carre projection,
    EPSG:4326, "unprojected profile".

    Such tiles are compatible with Google Earth (as any other EPSG:4326 rasters)
    and you can overlay the tiles on top of OpenLayers base map.

    Pixel and tile coordinates are in TMS notation (origin [0,0] in bottom-left).

    What coordinate conversions do we need for TMS Global Geodetic tiles?

      Global Geodetic tiles are using geodetic coordinates (latitude,longitude)
      directly as planar coordinates XY (it is also called Unprojected or Plate
      Carre). We need only scaling to pixel pyramid and cutting to tiles.
      Pyramid has on top level two tiles, so it is not square but rectangle.
      Area [-180,-90,180,90] is scaled to 512x256 pixels.
      TMS has coordinate origin (for pixels and tiles) in bottom-left corner.
      Rasters are in EPSG:4326 and therefore are compatible with Google Earth.

         LatLon      <->      Pixels      <->     Tiles

     WGS84 coordinates   Pixels in pyramid  Tiles in pyramid
         lat/lon         XY pixels Z zoom      XYZ from TMS
        EPSG:4326
         .----.                ----
        /      \     <->    /--------/    <->      TMS
        \      /         /--------------/
         -----        /--------------------/
       WMS, KML    Web Clients, Google Earth  TileMapService
    """

    def __init__(self, tmscompatible, tileSize=256):
        self.tileSize = tileSize
        if tmscompatible is not None:
            # Defaults the resolution factor to 0.703125 (2 tiles @ level 0)
            # Adhers to OSGeo TMS spec
            # http://wiki.osgeo.org/wiki/Tile_Map_Service_Specification#global-geodetic
            self.resFact = 180.0 / self.tileSize
        else:
            # Defaults the resolution factor to 1.40625 (1 tile @ level 0)
            # Adheres OpenLayers, MapProxy, etc default resolution for WMTS
            self.resFact = 360.0 / self.tileSize

    def LonLatToPixels(self, lon, lat, zoom):
        "Converts lon/lat to pixel coordinates in given zoom of the EPSG:4326 pyramid"

        res = self.resFact / 2**zoom
        px = (180 + lon) / res
        py = (90 + lat) / res
        return px, py

    def PixelsToTile(self, px, py):
        "Returns coordinates of the tile covering region in pixel coordinates"

        tx = int(math.ceil(px / float(self.tileSize)) - 1)
        ty = int(math.ceil(py / float(self.tileSize)) - 1)
        return tx, ty

    def LonLatToTile(self, lon, lat, zoom):
        "Returns the tile for zoom which covers given lon/lat coordinates"

        px, py = self.LonLatToPixels(lon, lat, zoom)
        return self.PixelsToTile(px, py)

    def Resolution(self, zoom):
        "Resolution (arc/pixel) for given zoom level (measured at Equator)"

        return self.resFact / 2**zoom

    def ZoomForPixelSize(self, pixelSize):
        "Maximal scaledown zoom of the pyramid closest to the pixelSize."

        for i in range(MAXZOOMLEVEL):
            if pixelSize > self.Resolution(i):
                if i != 0:
                    return i - 1
                else:
                    return 0    # We don't want to scale up

    def TileBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile"
        res = self.resFact / 2**zoom
        return (
            tx * self.tileSize * res - 180,
            ty * self.tileSize * res - 90,
            (tx + 1) * self.tileSize * res - 180,
            (ty + 1) * self.tileSize * res - 90
        )

    def TileLatLonBounds(self, tx, ty, zoom):
        "Returns bounds of the given tile in the SWNE form"
        b = self.TileBounds(tx, ty, zoom)
        return (b[1], b[0], b[3], b[2])


class TileDetail(object):
    """
        切片配置详细信息
    """
    tx = 0
    ty = 0
    tz = 0
    rx = 0
    ry = 0
    rxsize = 0
    rysize = 0
    wx = 0
    wy = 0
    wxsize = 0
    wysize = 0
    querysize = 0

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])

    def __unicode__(self):
        return "TileDetail %s\n%s\n%s\n" % (self.tx, self.ty, self.tz)

    def __str__(self):
        return "TileDetail %s\n%s\n%s\n" % (self.tx, self.ty, self.tz)

    def __repr__(self):
        return "TileDetail %s\n%s\n%s\n" % (self.tx, self.ty, self.tz)


class TileJobInfo(object):
    """
    切片任务信息
    Plain object to hold tile job configuration for a dataset
    """
    src_file = ""
    nb_data_bands = 0
    output_file_path = ""
    tile_extension = ""
    tile_size = 0
    tile_driver = None
    kml = False
    tminmax = []
    tminz = 0
    tmaxz = 0
    in_srs_wkt = 0
    out_geo_trans = []
    ominy = 0
    is_epsg_4326 = False
    options = None

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])

    def __unicode__(self):
        return "TileJobInfo %s\n" % (self.src_file)

    def __str__(self):
        return "TileJobInfo %s\n" % (self.src_file)

    def __repr__(self):
        return "TileJobInfo %s\n" % (self.src_file)


class GDAL2Tiles(object):
    """
        gdal2tiles类主体
        1、打开数据源
        2、生成元数据
        3、生成底层基础切片
    """
    def __init__(self, input_file, output_folder, options):
        """Constructor function - initialization"""
        self.out_drv = None
        self.mem_drv = None
        self.warped_input_dataset = None
        self.out_srs = None
        self.nativezoom = None
        self.tminmax = None
        self.tsize = None
        self.mercator = None
        self.geodetic = None
        self.alphaband = None
        self.dataBandsCount = None
        self.out_gt = None
        self.tileswne = None
        self.swne = None
        self.ominx = None
        self.omaxx = None
        self.omaxy = None
        self.ominy = None

        self.input_file = None
        self.output_folder = None

        # Tile format
        self.tilesize = 256
        self.tiledriver = 'PNG'
        self.tileext = 'png'
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_vrt_filename = os.path.join(
            self.tmp_dir, str(uuid4()) + '.vrt')

        # Should we read bigger window of the input raster and scale it down?
        # Note: Modified later by open_input()
        # Not for 'near' resampling
        # Not for Wavelet based drivers (JPEG2000, ECW, MrSID)
        # Not for 'raster' profile
        self.scaledquery = True
        # How big should be query window be for scaling down
        # Later on reset according the chosen resampling algorightm
        self.querysize = 4 * self.tilesize

        # Should we use Read on the input file for generating overview tiles?
        # Note: Modified later by open_input()
        # Otherwise the overview tiles are generated from existing underlying tiles
        self.overviewquery = False

        self.input_file = input_file
        self.output_folder = output_folder
        self.options = options

        if self.options.resampling == 'near':
            self.querysize = self.tilesize

        elif self.options.resampling == 'bilinear':
            self.querysize = self.tilesize * 2

        # User specified zoom levels
        self.tminz = None
        self.tmaxz = None

        if isinstance(self.options.zoom, (list, tuple)):
            self.tminz = self.options.zoom[0]
            self.tmaxz = self.options.zoom[1]
        elif isinstance(self.options.zoom, int):
            self.tminz = self.options.zoom
            self.tmaxz = self.tminz
        elif self.options.zoom:
            minmax = self.options.zoom.split('-', 1)
            minmax.extend([''])
            zoom_min, zoom_max = minmax[:2]
            self.tminz = int(zoom_min)
            if zoom_max:
                self.tmaxz = int(zoom_max)
            else:
                self.tmaxz = int(zoom_min)

        # KML generation
        self.kml = self.options.kml

    # -------------------------------------------------------------------------
    def open_input(self):
        """
        打开待切片的文件,根据不同的坐标系计算不同等级下该影像的范围
        Initialization of the input raster, reprojection if necessary"""
        gdal.AllRegister()

        self.out_drv = gdal.GetDriverByName(self.tiledriver)
        self.mem_drv = gdal.GetDriverByName('MEM')

        if not self.out_drv:
            raise Exception("The '%s' driver was not found, is it available in this GDAL build?",
                            self.tiledriver)
        if not self.mem_drv:
            raise Exception(
                "The 'MEM' driver was not found, is it available in this GDAL build?")

        # Open the input file

        if self.input_file:
            input_dataset = gdal.Open(self.input_file, gdal.GA_ReadOnly)
        else:
            raise Exception("No input file was specified")

        if self.options.verbose:
            print("Input file:",
                  "( %sP x %sL - %s bands)" % (input_dataset.RasterXSize,
                                               input_dataset.RasterYSize,
                                               input_dataset.RasterCount))

        if not input_dataset:
            # Note: GDAL prints the ERROR message too
            exit_with_error(
                "It is not possible to open the input file '%s'." % self.input_file)

        # Read metadata from the input file
        if input_dataset.RasterCount == 0:
            exit_with_error("Input file '%s' has no raster band" %
                            self.input_file)

        if input_dataset.GetRasterBand(1).GetRasterColorTable():
            exit_with_error(
                "Please convert this file to RGB/RGBA and run gdal2tiles on the result.",
                "From paletted file you can create RGBA file (temp.vrt) by:\n"
                "gdal_translate -of vrt -expand rgba %s temp.vrt\n"
                "then run:\n"
                "gdal2tiles temp.vrt" % self.input_file
            )

        in_nodata = setup_no_data_values(input_dataset, self.options)

        if self.options.verbose:
            print("Preprocessed file:",
                  "( %sP x %sL - %s bands)" % (input_dataset.RasterXSize,
                                               input_dataset.RasterYSize,
                                               input_dataset.RasterCount))

        in_srs, self.in_srs_wkt = setup_input_srs(input_dataset, self.options)

        self.out_srs = setup_output_srs(in_srs, self.options)

        # If input and output reference systems are different, we reproject the input dataset into
        # the output reference system for easier manipulation

        self.warped_input_dataset = None

        if self.options.profile in ('mercator', 'geodetic'):

            if not in_srs:
                exit_with_error(
                    "Input file has unknown SRS.",
                    "Use --s_srs ESPG:xyz (or similar) to provide source reference system.")

            if not has_georeference(input_dataset):
                exit_with_error(
                    "There is no georeference - neither affine transformation (worldfile) "
                    "nor GCPs. You can generate only 'raster' profile tiles.",
                    "Either gdal2tiles with parameter -p 'raster' or use another GIS "
                    "software for georeference e.g. gdal_transform -gcp / -a_ullr / -a_srs"
                )

            if ((in_srs.ExportToProj4() != self.out_srs.ExportToProj4()) or
                    (input_dataset.GetGCPCount() != 0)):
                self.warped_input_dataset = reproject_dataset(
                    input_dataset, in_srs, self.out_srs)

                if in_nodata:
                    self.warped_input_dataset = update_no_data_values(
                        self.warped_input_dataset, in_nodata, options=self.options)
                else:
                    self.warped_input_dataset = update_alpha_value_for_non_alpha_inputs(
                        self.warped_input_dataset, options=self.options)

            if self.warped_input_dataset and self.options.verbose:
                print("Projected file:", "tiles.vrt", "( %sP x %sL - %s bands)" % (
                    self.warped_input_dataset.RasterXSize,
                    self.warped_input_dataset.RasterYSize,
                    self.warped_input_dataset.RasterCount))

        if not self.warped_input_dataset:
            self.warped_input_dataset = input_dataset

        self.warped_input_dataset.GetDriver().CreateCopy(self.tmp_vrt_filename,
                                                         self.warped_input_dataset)

        # Get alpha band (either directly or from NODATA value)
        self.alphaband = self.warped_input_dataset.GetRasterBand(
            1).GetMaskBand()
        self.dataBandsCount = nb_data_bands(self.warped_input_dataset)

        # KML test
        self.isepsg4326 = False
        srs4326 = osr.SpatialReference()
        srs4326.ImportFromEPSG(4326)
        if self.out_srs and srs4326.ExportToProj4() == self.out_srs.ExportToProj4():
            self.kml = True
            self.isepsg4326 = True
            if self.options.verbose:
                print("KML autotest OK!")

        # Read the georeference
        self.out_gt = self.warped_input_dataset.GetGeoTransform()

        # Test the size of the pixel

        # Report error in case rotation/skew is in geotransform (possible only in 'raster' profile)
        if (self.out_gt[2], self.out_gt[4]) != (0, 0):
            exit_with_error("Georeference of the raster contains rotation or skew. "
                            "Such raster is not supported. Please use gdalwarp first.")

        # Here we expect: pixel is square, no rotation on the raster

        # Output Bounds - coordinates in the output SRS
        # ominx与omaxy为左上角位置，omaxx与ominy为右下角位置
        self.ominx = self.out_gt[0]
        self.omaxx = self.out_gt[0] + \
            self.warped_input_dataset.RasterXSize * self.out_gt[1]
        self.omaxy = self.out_gt[3]
        self.ominy = self.out_gt[3] - \
            self.warped_input_dataset.RasterYSize * self.out_gt[1]
        # Note: maybe round(x, 14) to avoid the gdal_translate behaviour, when 0 becomes -1e-15

        if self.options.verbose:
            print("Bounds (output srs):", round(self.ominx, 13),
                  self.ominy, self.omaxx, self.omaxy)

        # Calculating ranges for tiles in different zoom levels
        if self.options.profile == 'mercator':

            self.mercator = GlobalMercator()

            # Function which generates SWNE in LatLong for given tile
            self.tileswne = self.mercator.TileLatLonBounds

            # Generate table with min max tile coordinates for all zoomlevels
            self.tminmax = list(range(0, 32))
            for tz in range(0, 32):
                tminx, tminy = self.mercator.MetersToTile(
                    self.ominx, self.ominy, tz)
                tmaxx, tmaxy = self.mercator.MetersToTile(
                    self.omaxx, self.omaxy, tz)
                # crop tiles extending world limits (+-180,+-90)
                tminx, tminy = max(0, tminx), max(0, tminy)
                tmaxx, tmaxy = min(2**tz - 1, tmaxx), min(2**tz - 1, tmaxy)
                self.tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)

            # TODO: Maps crossing 180E (Alaska?)
            # 每一等级下的左上角与右下角的位置
            print(self.tminmax)
            # Get the minimal zoom level (map covers area equivalent to one tile)
            # 根据像素以及每个切片的大小计算推荐最小等级
            if self.tminz is None:
                self.tminz = self.mercator.ZoomForPixelSize(
                    self.out_gt[1] *
                    max(self.warped_input_dataset.RasterXSize,
                        self.warped_input_dataset.RasterYSize) /
                    float(self.tilesize))

            # Get the maximal zoom level
            # (closest possible zoom level up on the resolution of raster)
            # 根据像素以及每个切片的大小计算推荐最大等级
            if self.tmaxz is None:
                # *************************tmaxz默认值增加2**********************************
                self.tmaxz = self.mercator.ZoomForPixelSize(self.out_gt[1]) + 2

            if self.options.verbose:
                print("----Mercator----")
                print("Bounds (latlong):",
                      self.mercator.MetersToLatLon(self.ominx, self.ominy),
                      self.mercator.MetersToLatLon(self.omaxx, self.omaxy))
                print('MinZoomLevel:', self.tminz)
                print("MaxZoomLevel:",
                      self.tmaxz,
                      "(",
                      self.mercator.Resolution(self.tmaxz),
                      ")")

        if self.options.profile == 'geodetic':

            self.geodetic = GlobalGeodetic(self.options.tmscompatible)

            # Function which generates SWNE in LatLong for given tile
            self.tileswne = self.geodetic.TileLatLonBounds

            # Generate table with min max tile coordinates for all zoomlevels
            self.tminmax = list(range(0, 32))
            for tz in range(0, 32):
                tminx, tminy = self.geodetic.LonLatToTile(
                    self.ominx, self.ominy, tz)
                tmaxx, tmaxy = self.geodetic.LonLatToTile(
                    self.omaxx, self.omaxy, tz)
                # crop tiles extending world limits (+-180,+-90)
                tminx, tminy = max(0, tminx), max(0, tminy)
                tmaxx, tmaxy = min(
                    2**(tz + 1) - 1, tmaxx), min(2**tz - 1, tmaxy)
                self.tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)

            # TODO: Maps crossing 180E (Alaska?)

            # Get the maximal zoom level
            # (closest possible zoom level up on the resolution of raster)
            if self.tminz is None:
                self.tminz = self.geodetic.ZoomForPixelSize(
                    self.out_gt[1] *
                    max(self.warped_input_dataset.RasterXSize,
                        self.warped_input_dataset.RasterYSize) /
                    float(self.tilesize))

            # Get the maximal zoom level
            # (closest possible zoom level up on the resolution of raster)
            if self.tmaxz is None:
                # *************************tmaxz默认值增加2**********************************
                self.tmaxz = self.geodetic.ZoomForPixelSize(self.out_gt[1]) + 2

            if self.options.verbose:
                print("Bounds (latlong):", self.ominx,
                      self.ominy, self.omaxx, self.omaxy)

        if self.options.profile == 'raster':

            def log2(x):
                return math.log10(x) / math.log10(2)

            self.nativezoom = int(
                max(math.ceil(log2(self.warped_input_dataset.RasterXSize / float(self.tilesize))),
                    math.ceil(log2(self.warped_input_dataset.RasterYSize / float(self.tilesize)))))

            if self.options.verbose:
                print("Native zoom of the raster:", self.nativezoom)

            # Get the minimal zoom level (whole raster in one tile)
            if self.tminz is None:
                self.tminz = 0

            # Get the maximal zoom level (native resolution of the raster)
            if self.tmaxz is None:
                # *************************tmaxz默认值增加2**********************************
                self.tmaxz = self.nativezoom + 2

            # Generate table with min max tile coordinates for all zoomlevels
            self.tminmax = list(range(0, self.tmaxz + 1))
            self.tsize = list(range(0, self.tmaxz + 1))
            for tz in range(0, self.tmaxz + 1):
                tsize = 2.0**(self.nativezoom - tz) * self.tilesize
                tminx, tminy = 0, 0
                tmaxx = int(
                    math.ceil(self.warped_input_dataset.RasterXSize / tsize)) - 1
                tmaxy = int(
                    math.ceil(self.warped_input_dataset.RasterYSize / tsize)) - 1
                self.tsize[tz] = math.ceil(tsize)
                self.tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)

            # Function which generates SWNE in LatLong for given tile
            if self.kml and self.in_srs_wkt:
                ct = osr.CoordinateTransformation(in_srs, srs4326)

                def rastertileswne(x, y, z):
                    # X-pixel size in level
                    pixelsizex = (2**(self.tmaxz - z) * self.out_gt[1])
                    west = self.out_gt[0] + x * self.tilesize * pixelsizex
                    east = west + self.tilesize * pixelsizex
                    south = self.ominy + y * self.tilesize * pixelsizex
                    north = south + self.tilesize * pixelsizex
                    if not self.isepsg4326:
                        # Transformation to EPSG:4326 (WGS84 datum)
                        west, south = ct.TransformPoint(west, south)[:2]
                        east, north = ct.TransformPoint(east, north)[:2]
                    return south, west, north, east

                self.tileswne = rastertileswne
            else:
                self.tileswne = lambda x, y, z: (0, 0, 0, 0)   # noqa

    def generate_metadata(self):
        """
        生成创建html的元数据
        Generation of main metadata files and HTML viewers (metadata related to particular
        tiles are generated during the tile processing).
        """

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        if self.options.profile == 'mercator':

            south, west = self.mercator.MetersToLatLon(self.ominx, self.ominy)
            north, east = self.mercator.MetersToLatLon(self.omaxx, self.omaxy)
            south, west = max(-85.05112878, south), max(-180.0, west)
            north, east = min(85.05112878, north), min(180.0, east)
            self.swne = (south, west, north, east)

            # Generate googlemaps.html
            if self.options.webviewer in ('all', 'google') and self.options.profile == 'mercator':
                if (not self.options.resume or not
                        os.path.exists(os.path.join(self.output_folder, 'googlemaps.html'))):
                    with open(os.path.join(self.output_folder, 'googlemaps.html'), 'wb') as f:
                        f.write(self.generate_googlemaps().encode('utf-8'))

            # Generate openlayers.html
            if self.options.webviewer in ('all', 'openlayers'):
                if (not self.options.resume or not
                        os.path.exists(os.path.join(self.output_folder, 'openlayers.html'))):
                    with open(os.path.join(self.output_folder, 'openlayers.html'), 'wb') as f:
                        f.write(self.generate_openlayers().encode('utf-8'))

            # Generate leaflet.html
            if self.options.webviewer in ('all', 'leaflet'):
                if (not self.options.resume or not
                        os.path.exists(os.path.join(self.output_folder, 'leaflet.html'))):
                    with open(os.path.join(self.output_folder, 'leaflet.html'), 'wb') as f:
                        f.write(self.generate_leaflet().encode('utf-8'))

        elif self.options.profile == 'geodetic':

            west, south = self.ominx, self.ominy
            east, north = self.omaxx, self.omaxy
            south, west = max(-90.0, south), max(-180.0, west)
            north, east = min(90.0, north), min(180.0, east)
            self.swne = (south, west, north, east)

            # Generate openlayers.html
            if self.options.webviewer in ('all', 'openlayers'):
                if (not self.options.resume or not
                        os.path.exists(os.path.join(self.output_folder, 'openlayers.html'))):
                    with open(os.path.join(self.output_folder, 'openlayers.html'), 'wb') as f:
                        f.write(self.generate_openlayers().encode('utf-8'))

        elif self.options.profile == 'raster':

            west, south = self.ominx, self.ominy
            east, north = self.omaxx, self.omaxy

            self.swne = (south, west, north, east)

            # Generate openlayers.html
            if self.options.webviewer in ('all', 'openlayers'):
                if (not self.options.resume or not
                        os.path.exists(os.path.join(self.output_folder, 'openlayers.html'))):
                    with open(os.path.join(self.output_folder, 'openlayers.html'), 'wb') as f:
                        f.write(self.generate_openlayers().encode('utf-8'))

        # Generate tilemapresource.xml.
        if not self.options.resume or not os.path.exists(os.path.join(self.output_folder, 'tilemapresource.xml')):
            with open(os.path.join(self.output_folder, 'tilemapresource.xml'), 'wb') as f:
                f.write(self.generate_tilemapresource().encode('utf-8'))

        if self.kml:
            # TODO: Maybe problem for not automatically generated tminz
            # The root KML should contain links to all tiles in the tminz level
            children = []
            xmin, ymin, xmax, ymax = self.tminmax[self.tminz]
            for x in range(xmin, xmax + 1):
                for y in range(ymin, ymax + 1):
                    children.append([x, y, self.tminz])

    def generate_base_tiles(self):
        """
        创建最底层的切片空间索引，即每个切片在影像中的位置以及大小，为切片做好准备
        Generation of the base tiles (the lowest in the pyramid) directly from the input raster
        """

        if not self.options.quiet:
            print("Generating Base Tiles:")

        if self.options.verbose:
            print('')
            print("Tiles generated from the max zoom level:")
            print("----------------------------------------")
            print('')

        # Set the bounds, 最大等级下的图像范围
        tminx, tminy, tmaxx, tmaxy = self.tminmax[self.tmaxz]

        ds = self.warped_input_dataset
        tilebands = self.dataBandsCount + 1
        querysize = self.querysize

        if self.options.verbose:
            print("dataBandsCount: ", self.dataBandsCount)
            print("tilebands: ", tilebands)
        # 最大等级下的长度乘宽度
        tcount = (1 + abs(tmaxx - tminx)) * (1 + abs(tmaxy - tminy))
        ti = 0

        tile_details = []
        tile_details_strs = "["

        # ***************z值增加一************************
        # 遍历获取最大等级下的每个切片的文件名称
        for tz in range(self.tmaxz, self.tminz - 1, -1):
            tminx, tminy, tmaxx, tmaxy = self.tminmax[tz]
            for ty in range(tmaxy, tminy - 1, -1):
                for tx in range(tminx, tmaxx + 1):

                    ti += 1

                    if self.options.profile == 'mercator':
                        # Tile bounds in EPSG:3857, 获取墨卡托投影下的影像范围。
                        b = self.mercator.TileBounds(tx, ty, tz)
                    elif self.options.profile == 'geodetic':
                        b = self.geodetic.TileBounds(tx, ty, tz)

                    # Don't scale up by nearest neighbour, better change the querysize
                    # to the native resolution (and return smaller query tile) for scaling

                    if self.options.profile in ('mercator', 'geodetic'):
                        rb, wb = self.geo_query(ds, b[0], b[3], b[2], b[1])

                        # Pixel size in the raster covering query geo extent
                        nativesize = wb[0] + wb[2]
                        # if self.options.verbose:
                        #     print("\tNative Extent (querysize",
                        #           nativesize, "): ", rb, wb)

                        # Tile bounds in raster coordinates for ReadRaster query
                        rb, wb = self.geo_query(
                            ds, b[0], b[3], b[2], b[1], querysize=querysize)

                        rx, ry, rxsize, rysize = rb
                        wx, wy, wxsize, wysize = wb

                    else:     # 'raster' profile:

                        # tilesize in raster coordinates for actual zoom
                        tsize = int(self.tsize[tz])
                        xsize = self.warped_input_dataset.RasterXSize     # size of the raster in pixels
                        ysize = self.warped_input_dataset.RasterYSize
                        if tz >= self.nativezoom:
                            querysize = self.tilesize

                        rx = (tx) * tsize
                        rxsize = 0
                        if tx == tmaxx:
                            rxsize = xsize % tsize
                        if rxsize == 0:
                            rxsize = tsize

                        rysize = 0
                        if ty == tmaxy:
                            rysize = ysize % tsize
                        if rysize == 0:
                            rysize = tsize
                        ry = ysize - (ty * tsize) - rysize

                        wx, wy = 0, 0
                        wxsize = int(rxsize / float(tsize) * self.tilesize)
                        wysize = int(rysize / float(tsize) * self.tilesize)
                        if wysize != self.tilesize:
                            wy = self.tilesize - wysize

                    # Read the source raster if anything is going inside the tile as per the computed
                    # geo_query，tile_details中记录每个最大等级下的每个切片的起始位置以及大小
                    tile_detail = TileDetail(
                            tx=tx, ty=ty, tz=tz, 
                            rx=rx, ry=ry, rxsize=rxsize, rysize=rysize, 
                            wx=wx, wy=wy, wxsize=wxsize, wysize=wysize, 
                            querysize=querysize,
                        )
                    tile_details_strs += dumps({ 
                        "tx": tx, "ty": ty, "tz": tz, 
                        "rx": rx, "ry": ry, "rxsize": rxsize, "rysize": rysize, 
                        "wx": wx, "wy": wy, "wxsize": wxsize, "wysize": wysize, 
                        "querysize": querysize,}) + ",\n"
                    tile_details.append(tile_detail)
            
        tile_details_strs += "]"
        conf = TileJobInfo(
            src_file=self.tmp_vrt_filename,
            nb_data_bands=self.dataBandsCount,
            output_file_path=self.output_folder,
            tile_extension=self.tileext,
            tile_driver=self.tiledriver,
            tile_size=self.tilesize,
            kml=self.kml,
            tminmax=self.tminmax,
            tminz=self.tminz,
            tmaxz=self.tmaxz,
            in_srs_wkt=self.in_srs_wkt,
            out_geo_trans=self.out_gt,
            ominy=self.ominy,
            is_epsg_4326=self.isepsg4326,
            options=self.options,
        )
        with open("./tileDetails.json", "w") as f:
            # tile_details_str = dumps(tile_details_strs)
            f.write(tile_details_strs)
            print("切片索引写入文件成功！")
        return conf, tile_details
    
    def geo_query(self, ds, ulx, uly, lrx, lry, querysize=0):
        """
        (rx, ry, rxsize, rysize)为获取该切片在图像中的位置以及大小
        For given dataset and query in cartographic coordinates returns parameters for ReadRaster()
        in raster coordinates and x/y shifts (for border tiles). If the querysize is not given, the
        extent is returned in the native resolution of dataset ds.

        raises Gdal2TilesError if the dataset does not contain anything inside this geo_query
        """
        geotran = ds.GetGeoTransform()
        rx = int((ulx - geotran[0]) / geotran[1] + 0.001)
        ry = int((uly - geotran[3]) / geotran[5] + 0.001)
        rxsize = int((lrx - ulx) / geotran[1] + 0.5)
        rysize = int((lry - uly) / geotran[5] + 0.5)

        if not querysize:
            wxsize, wysize = rxsize, rysize
        else:
            wxsize, wysize = querysize, querysize

        # Coordinates should not go out of the bounds of the raster
        wx = 0
        if rx < 0:
            rxshift = abs(rx)
            wx = int(wxsize * (float(rxshift) / rxsize))
            wxsize = wxsize - wx
            rxsize = rxsize - int(rxsize * (float(rxshift) / rxsize))
            rx = 0
        if rx + rxsize > ds.RasterXSize:
            wxsize = int(wxsize * (float(ds.RasterXSize - rx) / rxsize))
            rxsize = ds.RasterXSize - rx

        wy = 0
        if ry < 0:
            ryshift = abs(ry)
            wy = int(wysize * (float(ryshift) / rysize))
            wysize = wysize - wy
            rysize = rysize - int(rysize * (float(ryshift) / rysize))
            ry = 0
        if ry + rysize > ds.RasterYSize:
            wysize = int(wysize * (float(ds.RasterYSize - ry) / rysize))
            rysize = ds.RasterYSize - ry

        return (rx, ry, rxsize, rysize), (wx, wy, wxsize, wysize)

    def generate_tilemapresource(self):
        """
        Template for tilemapresource.xml. Returns filled string. Expected variables:
          title, north, south, east, west, isepsg4326, projection, publishurl,
          zoompixels, tilesize, tileformat, profile
        """

        args = {}
        args['title'] = self.options.title
        args['south'], args['west'], args['north'], args['east'] = self.swne
        args['tilesize'] = self.tilesize
        args['tileformat'] = self.tileext
        args['publishurl'] = self.options.url
        args['profile'] = self.options.profile

        if self.options.profile == 'mercator':
            args['srs'] = "EPSG:3857"
        elif self.options.profile == 'geodetic':
            args['srs'] = "EPSG:4326"
        elif self.options.s_srs:
            args['srs'] = self.options.s_srs
        elif self.out_srs:
            args['srs'] = self.out_srs.ExportToWkt()
        else:
            args['srs'] = ""

        s = """<?xml version="1.0" encoding="utf-8"?>
        <TileMap version="1.0.0" tilemapservice="http://tms.osgeo.org/1.0.0">
        <Title>%(title)s</Title>
        <Abstract></Abstract>
        <SRS>%(srs)s</SRS>
        <BoundingBox minx="%(west).14f" miny="%(south).14f" maxx="%(east).14f" maxy="%(north).14f"/>
        <Origin x="%(west).14f" y="%(south).14f"/>
        <TileFormat width="%(tilesize)d" height="%(tilesize)d" mime-type="image/%(tileformat)s" extension="%(tileformat)s"/>
        <TileSets profile="%(profile)s">
        """ % args    # noqa
        for z in range(self.tminz, self.tmaxz + 1):
            if self.options.profile == 'raster':
                s += """        <TileSet href="%s%d" units-per-pixel="%.14f" order="%d"/>\n""" % (
                    args['publishurl'], z, (2**(self.nativezoom - z) * self.out_gt[1]), z)
            elif self.options.profile == 'mercator':
                s += """        <TileSet href="%s%d" units-per-pixel="%.14f" order="%d"/>\n""" % (
                    args['publishurl'], z, 156543.0339 / 2**z, z)
            elif self.options.profile == 'geodetic':
                s += """        <TileSet href="%s%d" units-per-pixel="%.14f" order="%d"/>\n""" % (
                    args['publishurl'], z, 0.703125 / 2**z, z)
        s += """      </TileSets>
        </TileMap>
        """
        return s


def worker_tile_details(input_file, output_folder, options, send_pipe=None):
    '''创建GDAL2Tiles的类，通过该类打开图像，生成元数据，获取切片的信息'''
    gdal2tiles = GDAL2Tiles(input_file, output_folder, options)
    gdal2tiles.open_input()
    gdal2tiles.generate_metadata()
    tile_job_info, tile_details = gdal2tiles.generate_base_tiles()
    return_data = (tile_job_info, tile_details)
    if send_pipe:
        send_pipe.send(return_data)

    return return_data


def get_tile_swne(tile_job_info, options):
    '''
        获取东西南北的范围值
    '''
    if options.profile == 'mercator':
        mercator = GlobalMercator()
        tile_swne = mercator.TileLatLonBounds
    elif options.profile == 'geodetic':
        geodetic = GlobalGeodetic(options.tmscompatible)
        tile_swne = geodetic.TileLatLonBounds
    elif options.profile == 'raster':
        srs4326 = osr.SpatialReference()
        srs4326.ImportFromEPSG(4326)
        if tile_job_info.kml and tile_job_info.in_srs_wkt:
            in_srs = osr.SpatialReference()
            in_srs.ImportFromWkt(tile_job_info.in_srs_wkt)
            ct = osr.CoordinateTransformation(in_srs, srs4326)

            def rastertileswne(x, y, z):
                pixelsizex = (2 ** (tile_job_info.tmaxz - z)
                              * tile_job_info.out_geo_trans[1])
                west = tile_job_info.out_geo_trans[0] + \
                    x * tile_job_info.tilesize * pixelsizex
                east = west + tile_job_info.tilesize * pixelsizex
                south = tile_job_info.ominy + y * tile_job_info.tilesize * pixelsizex
                north = south + tile_job_info.tilesize * pixelsizex
                if not tile_job_info.is_epsg_4326:
                    # Transformation to EPSG:4326 (WGS84 datum)
                    west, south = ct.TransformPoint(west, south)[:2]
                    east, north = ct.TransformPoint(east, north)[:2]
                return south, west, north, east

            tile_swne = rastertileswne
        else:
            def tile_swne(x, y, z): return (0, 0, 0, 0)   # noqa
    else:
        def tile_swne(x, y, z): return (0, 0, 0, 0)   # noqa

    return tile_swne



def multi_threaded_tiling(input_file, output_folder, **options):
    """多进程切片
    Generate tiles with multi processing."""
    # 对传入的参数进行处理
    options = process_options(input_file, output_folder, options)

    nb_processes = options.nb_processes or 1
    (conf_receiver, conf_sender) = Pipe(False)

    if options.verbose:
        print("Begin tiles details calc")
    # 启动一个进程进行最底层切片索引创建
    p = Process(target=worker_tile_details,
                args=[input_file, output_folder, options],
                kwargs={"send_pipe": conf_sender})
    p.start()
    # Make sure to consume the queue before joining. If the payload is too big, it won't be put in
    # one go in the queue and therefore the sending process will never finish, waiting for space in
    # the queue to send data
    # 获取worker_tile_details返回信息
    conf, tile_details = conf_receiver.recv()
    # 主进程等待该进程执行完毕后在执行下面的程序
    p.join()

    if options.verbose:
        print("Tiles details calc complete.")
    # Have to create the Queue through a multiprocessing.Manager to get a Queue Proxy,
    # otherwise you can't pass it as a param in the method invoked by the pool...
    # manager = Manager()
    # queue = manager.Queue()
    # pool = Pool(processes=nb_processes)
    # # TODO: gbataille - check the confs for which each element is an array... one useless level?
    # # TODO: gbataille - assign an ID to each job for print in verbose mode "ReadRaster Extent ..."
    # # TODO: gbataille - check memory footprint and time on big image. are they opened x times
    # for tile_detail in tile_details:
    #     pool.apply_async(create_base_tile,
    #                      (conf, tile_detail), {"queue": queue})
    
    # # ************* 获取传入文件名称 *****************
    # path_, file_ = os.path.split(input_file)
    # if options.verbose and not options.quiet:
    # # if not options.verbose and not options.quiet:
    #     # *************创建新的进程打印切片进度 获取传入文件名称 *****************
    #     p = Process(target=progress_printer_thread, args=[
    #                 queue, len(tile_details), file_ + "_tile"])
    #     p.start()

    # pool.close()
    # pool.join()     # Jobs finished
    # if not options.verbose and not options.quiet:
    #     p.join()        # Traces done
    
    # # 生成总览图
    # create_overview_tiles(conf, output_folder, options, file_ + "_overview")
    # 删除临时文件
    shutil.rmtree(os.path.dirname(conf.src_file))
    print("清除临时文件...")
    if os.path.exists(input_file):
        os.remove(input_file)


def generate_tiles(input_file, output_folder, **options):
    """Generate tiles from input file.

    Arguments:
        ``input_file`` (str): Path to input file.

        ``output_folder`` (str): Path to output folder.

        ``options``: Tile generation options.

    Options:
        ``profile`` (str): Tile cutting profile (mercator,geodetic,raster) - default
            'mercator' (Google Maps compatible)

        ``resampling`` (str): Resampling method (average,near,bilinear,cubic,cubicsp
            line,lanczos,antialias) - default 'average'

        ``s_srs``: The spatial reference system used for the source input data

        ``zoom``: Zoom levels to render; format: `[int min, int max]`,
            `'min-max'` or `int/str zoomlevel`.

        ``resume`` (bool): Resume mode. Generate only missing files.

        ``srcnodata``: NODATA transparency value to assign to the input data

        ``tmscompatible`` (bool): When using the geodetic profile, specifies the base
            resolution as 0.703125 or 2 tiles at zoom level 0.

        ``verbose`` (bool): Print status messages to stdout

        ``kml`` (bool): Generate KML for Google Earth - default for 'geodetic'
                        profile and 'raster' in EPSG:4326. For a dataset with
                        different projection use with caution!

        ``url`` (str): URL address where the generated tiles are going to be published

        ``webviewer`` (str): Web viewer to generate (all,google,openlayers,none) -
            default 'all'

        ``title`` (str): Title of the map

        ``copyright`` (str): Copyright for the map

        ``googlekey`` (str): Google Maps API key from
            http://code.google.com/apis/maps/signup.html

        ``bingkey`` (str): Bing Maps API key from https://www.bingmapsportal.com/

        ``nb_processes``: Number of processes to use for tiling.
    """
    if options:
        nb_processes = options.get('nb_processes') or 2
    else:
        nb_processes = 2

    multi_threaded_tiling(input_file, output_folder, **options)

    # python gdal2tiles_spatialIndex.py 


if __name__ == "__main__":
    generate_tiles("", "", {})