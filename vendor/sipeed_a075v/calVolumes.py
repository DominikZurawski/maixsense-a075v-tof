from PIL import Image, ImageDraw
import requests
import matplotlib.pyplot as plt
import struct
import numpy as np
import cv2


def depth2xyz(xp, yp, z, fx, fy, cx, cy, depth_scale=1000):
    # h,w=np.mgrid[0:depth_map.shape[0],0:depth_map.shape[1]]
    z = z/depth_scale
    x = (xp-cx)*z/fx
    y = (yp-cy)*z/fy
    # xyz=np.dstack((x,y,z))
    # xyz=cv2.rgbd.depthTo3d(depth_map,depth_cam_matrix)
    return [x, y, z]


def polygon_area(polygon):
    area = 0
    q = polygon[-1]
    for p in polygon:
        area += p[0] * q[1] - p[1] * q[0]
        q = p
    return abs(area) / 2.0


diff_low = 50
diff_high = 500
fx = 2.265142e+02
fy = 2.278584e+02
cx = 1.637246e+02  # cx
cy = 1.233738e+02  # cy


def cal_volume(d_bk, d_bg):
    img_h, img_w = d_bk.shape[0], d_bk.shape[1]
    d_bk = d_bk.astype(np.float32)/4  # cvt to mm
    d_bg = d_bg.astype(np.float32)/4

    diff = (d_bg-d_bk).astype(np.int16)
    diff1 = diff.copy()
    diff1 = np.where(diff1 < diff_low, 0, diff1)
    diff1 = np.where(diff1 > diff_high, 0, diff1)
    diff1 = (np.where(diff1 > 0, 1, 0)*255).astype(np.uint8)
    plt.imshow(diff1)

    # print(d_bk.shape) (240, 320)
    output = np.zeros((img_h, img_w, 3), np.uint8)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        diff1, connectivity=8)
    # print('num_labels = ',num_labels)
    # 连通域的信息：对应各个轮廓的x、y、width、height和面积
    # print('stats = ',stats)
    for i in range(5):
        max_label = 1+np.argmax(stats[1:, 4])
        # print('stats[max_label] = ', stats[max_label])
        if i > 0 and stats[max_label][4] < 700:
            break
        max_stat = stats[max_label]
        stats[max_label][4] = 0

        mask = (labels == max_label)
        # (np.random.rand(3)*255).astype(np.uint8)
        output[:, :, :][mask] = [200, 0, 0]
        # plt.imshow(output)
        volumes = []
        # points = []
        # areas = []
        for yp in range(img_h):
            for xp in range(img_w):
                if mask[yp, xp]:
                    x1, y1, z1 = depth2xyz(
                        xp, yp, d_bk[yp, xp], fx, fy, cx, cy, depth_scale=1)
                    x0, y0, z0 = depth2xyz(
                        xp, yp, d_bg[yp, xp], fx, fy, cx, cy, depth_scale=1)

                    x = xp-1
                    if x < 0:
                        x = 0
                    y = yp
                    xl, yl, zl = depth2xyz(
                        x, y, d_bk[y, x], fx, fy, cx, cy, depth_scale=1)
                    x = xp+1
                    if x >= img_w:
                        x = img_w-1
                    y = yp
                    xr, yr, zr = depth2xyz(
                        x, y, d_bk[y, x], fx, fy, cx, cy, depth_scale=1)
                    x = xp
                    y = yp-1
                    if y < 0:
                        y = 0
                    xt, yt, zt = depth2xyz(
                        x, y, d_bk[y, x], fx, fy, cx, cy, depth_scale=1)
                    x = xp
                    y = yp+1
                    if y >= img_h:
                        y = img_h-1
                    xb, yb, zb = depth2xyz(
                        x, y, d_bk[y, x], fx, fy, cx, cy, depth_scale=1)
                    area_a = polygon_area(
                        [[xt, yt], [xl, yl], [xb, yb], [xr, yr]])/2

                    dz = z0-z1
                    dx = z1/fx
                    dy = z1/fy
                    area_b = dx*dy*2/2

                    area = (area_a+area_b)/2  # avg get better acc
                    volume = area*dz
                    # areas.append(area)
                    volumes.append(volume)
                    # points.append((x1, y1, dz))
        # areas = np.array(areas)
        volumes = np.array(volumes)
        # points = np.array(points)

        res = "{}:{} cm3".format(i, int(np.sum(volumes)/1000))
        # print(res)

        img_pil = Image.fromarray(output)
        draw = ImageDraw.Draw(img_pil)
        draw.rectangle([(max_stat[0], max_stat[1]),
                       (max_stat[0] + max_stat[2], max_stat[1] + max_stat[3])], outline="red")
        draw.text((max_stat[0], max_stat[1]),  res, fill=(255, 255, 255))
        output = np.array(img_pil)

    return output


def frame_config_decode(frame_config):
    '''
        @frame_config bytes

        @return fields, tuple (trigger_mode, deep_mode, deep_shift, ir_mode, status_mode, status_mask, rgb_mode, rgb_res, expose_time)
    '''
    return struct.unpack("<BBBBBBBBi", frame_config)


def frame_config_encode(trigger_mode=1, deep_mode=1, deep_shift=255, ir_mode=1, status_mode=2, status_mask=7, rgb_mode=1, rgb_res=0, expose_time=0):
    return struct.pack("<BBBBBBBBi",
                       trigger_mode, deep_mode, deep_shift, ir_mode, status_mode, status_mask, rgb_mode, rgb_res, expose_time)


def frame_payload_decode(frame_data: bytes, with_config: tuple):
    deep_data_size, rgb_data_size = struct.unpack("<ii", frame_data[:8])
    frame_payload = frame_data[8:]
    # 0:16bit 1:8bit, resolution: 320*240
    deepth_size = (320*240*2) >> with_config[1]
    deepth_img = struct.unpack("<%us" % deepth_size, frame_payload[:deepth_size])[
        0] if 0 != deepth_size else None
    frame_payload = frame_payload[deepth_size:]

    # 0:16bit 1:8bit, resolution: 320*240
    ir_size = (320*240*2) >> with_config[3]
    ir_img = struct.unpack("<%us" % ir_size, frame_payload[:ir_size])[
        0] if 0 != ir_size else None
    frame_payload = frame_payload[ir_size:]

    status_size = (320*240//8) * (16 if 0 == with_config[4] else
                                  2 if 1 == with_config[4] else 8 if 2 == with_config[4] else 1)
    status_img = struct.unpack("<%us" % status_size, frame_payload[:status_size])[
        0] if 0 != status_size else None
    frame_payload = frame_payload[status_size:]

    assert(deep_data_size == deepth_size+ir_size+status_size)

    rgb_size = len(frame_payload)
    assert(rgb_data_size == rgb_size)
    rgb_img = struct.unpack("<%us" % rgb_size, frame_payload[:rgb_size])[
        0] if 0 != rgb_size else None

    if (not rgb_img is None) and (1 == with_config[6]):
        jpeg = cv2.imdecode(np.frombuffer(
            rgb_img, 'uint8', rgb_size), cv2.IMREAD_COLOR)
        if not jpeg is None:
            rgb = cv2.cvtColor(jpeg, cv2.COLOR_BGR2RGB)
            rgb_img = rgb.tobytes()
        else:
            rgb_img = None

    return (deepth_img, ir_img, status_img, rgb_img)


HOST = '192.168.233.233'
PORT = 80


def post_encode_config(config=frame_config_encode(), host=HOST, port=PORT):
    r = requests.post('http://{}:{}/set_cfg'.format(host, port), config)
    if(r.status_code == requests.codes.ok):
        return True
    return False


def get_frame_from_http(host=HOST, port=PORT):
    r = requests.get('http://{}:{}/getdeep'.format(host, port))
    if(r.status_code == requests.codes.ok):
        # print('Get deep image')
        deepimg = r.content
        # print('Length={}'.format(len(deepimg)))
        (frameid, stamp_msec) = struct.unpack('<QQ', deepimg[0:8+8])
        # print((frameid, stamp_msec/1000))
        return deepimg


def show_frame(fig, frame_data: bytes):
    config = frame_config_decode(frame_data[16:16+12])
    frame_bytes = frame_payload_decode(frame_data[16+12:], config)

    depth = np.frombuffer(frame_bytes[0], 'uint16' if 0 == config[1] else 'uint8').reshape(
        240, 320) if frame_bytes[0] else None

    # ir = np.frombuffer(frame_bytes[1], 'uint16' if 0 == config[3] else 'uint8').reshape(
    #     240, 320) if frame_bytes[1] else None

    # status = np.frombuffer(frame_bytes[2], 'uint16' if 0 == config[4] else 'uint8').reshape(
    #     240, 320) if frame_bytes[2] else None

    rgb = np.frombuffer(frame_bytes[3], 'uint8').reshape(
        (480, 640, 3)) if frame_bytes[3] else None

    ax1 = fig.add_subplot(122)
    if not depth is None:
        # center_dis = depth[240//2, 320//2]
        # if 0 == config[1]:
        #     print("%f mm" % (center_dis/4))
        # else:
        #     print("%f mm" % ((center_dis/5.1) ** 2))
        # depth = depth.copy()

        # l,r= 200,5000
        # depth_f = ((depth.astype('float64') - l) * (65535 / (r - l)))
        # depth_f[np.where(depth_f < 0)] = 0
        # depth_f[np.where(depth_f > 65535)] = 65535

        # depth = depth_f.astype(depth.dtype)

        # depth[240//2, 320//2 - 5:320//2+5] = 0x00
        # depth[240//2-5:240//2+5, 320//2] = 0x00

        if not UPDATE_BG[1] is None:
            ax1.imshow(cal_volume(depth, UPDATE_BG[1]))
        else:
            ax1.imshow(depth)

        if UPDATE_BG[0]:
            UPDATE_BG[1] = depth

    # ax2 = fig.add_subplot(222)
    # if not ir is None:
    #     ax2.imshow(ir, cmap='gray')
    # ax3 = fig.add_subplot(223)
    # if not status is None:
    #     ax3.imshow(status)
    ax4 = fig.add_subplot(121)
    if not rgb is None:
        ax4.imshow(rgb)


UPDATE_BG = [False, None]

if post_encode_config(frame_config_encode(1, 0, 255, 0, 2, 7, 1, 0, 0)):
    # 打开交互模式
    def on_key_press(event):
        if event.key == ' ':
            UPDATE_BG[0] = True
        elif event.key == 'c':
            UPDATE_BG[1] = None

    plt.ion()
    figsize = (12, 12)
    fig = plt.figure('2D frame', figsize=figsize)
    fig.canvas.mpl_connect('key_press_event', on_key_press)

    print("按下空格键更新背景图，按下c键清空背景图")
    while True:
        p = get_frame_from_http()
        show_frame(fig, p)
        if UPDATE_BG[0]:
            UPDATE_BG[0] = False
            print("update bg success!")
        # 停顿时间
        plt.pause(0.001)
        # 清除当前画布
        fig.clf()

    plt.ioff()
