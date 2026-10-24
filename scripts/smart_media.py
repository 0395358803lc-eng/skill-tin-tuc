#!/usr/bin/env python3
"""Stage19 smart focal detector; local OpenCV face + visual saliency + motion.

Never identifies a person or certifies editorial relevance. Safe manual override.
"""
from __future__ import annotations
import json,math
from pathlib import Path

def bounded(x:float)->float:return max(0.,min(1.,float(x)))

def _opencv():
    try:
        import cv2
        return cv2
    except ImportError:
        return None

def center_from_rgb(image)->dict:
    from PIL import Image, ImageFilter, ImageStat
    cv2=_opencv()
    if cv2:
        import numpy as np
        arr=np.asarray(image.convert('RGB'))
        gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
        model=cv2.CascadeClassifier(str(Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml'))
        found=model.detectMultiScale(gray,scaleFactor=1.13,minNeighbors=4,minSize=(20,20))
        if len(found):
            faces=sorted(found,key=lambda x:int(x[2])*int(x[3]),reverse=True)
            x,y,w,h=[int(v) for v in faces[0]]
            return {'focal_x':round(bounded((x+w/2)/image.width),4),
                    'focal_y':round(bounded((y+h/2)/image.height),4),
                    'method':'LOCAL_HAAR_FACE_DETECTION','face_count':len(found),'confidence':'MEDIUM_HEURISTIC',
                    'subjects_in_frame':len(found)}
    # Edge-energy weighted saliency, biased to central field.
    work=image.convert('L').resize((min(320,image.width),min(180,image.height)))
    edges=work.filter(ImageFilter.FIND_EDGES)
    import numpy as np
    pixels=np.asarray(edges,dtype='float32')
    h,w=pixels.shape
    yy,xx=np.mgrid[0:h,0:w]
    bias=1-0.52*np.minimum(1,np.sqrt(((xx/w-.5)*1.1)**2+((yy/h-.5)*1.1)**2))
    strength=np.maximum(0,pixels-18)**1.35*bias
    denom=float(strength.sum())
    if denom<1.e-4:
        return {'focal_x':.5,'focal_y':.5,'method':'CENTER_FALLBACK_LOW_TEXTURE',
                'face_count':0,'confidence':'LOW','subjects_in_frame':0}
    return {'focal_x':round(bounded(float((strength*xx).sum()/denom)/w),4),
            'focal_y':round(bounded(float((strength*yy).sum()/denom)/h),4),
            'method':'LOCAL_EDGE_SALIENCY_HEURISTIC','face_count':0,
            'confidence':'LOW','subjects_in_frame':0}

def image_focus(path:Path)->dict:
    from PIL import Image,ImageOps
    with Image.open(path) as source:
        w,h=source.size
        if not 80<=w<=16000 or not 80<=h<=16000:raise ValueError('invalid media dimensions')
        img=ImageOps.exif_transpose(source).convert('RGB')
        # Limit face detection CPU on large photos; preserve coordinates.
        scale=min(1.,960/max(img.size))
        if scale<1:img=img.resize((max(1,round(img.width*scale)),max(1,round(img.height*scale))))
        r=center_from_rgb(img)
        return {**r,'source_width':w,'source_height':h,'automatic_focus_is_editorial_suggestion':True}

def video_focus(path:Path,seconds:float,samples:int=7)->dict:
    cv2=_opencv()
    if not cv2:raise RuntimeError('video Smart Crop requires local OpenCV; install in runtime, not Skill')
    if not 0<seconds<=600 or not 3<=samples<=12:raise ValueError('invalid clip sampling parameters')
    cap=cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():raise ValueError('cannot decode video for Smart Crop')
        total=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps=cap.get(cv2.CAP_PROP_FPS)
        if not fps or not 0<fps<240 or total<1:raise ValueError('invalid frame count / fps')
        source_duration=total/fps
        if source_duration<=0:raise ValueError('source has no frames')
        from PIL import Image
        trajectory=[]
        previous=None
        for i in range(samples):
            # Loop safely through source if shorter than the story narration.
            t=max(0.,min(seconds,(i+.5)*seconds/samples))
            seek=min(source_duration-.0001,t%source_duration)
            cap.set(cv2.CAP_PROP_POS_MSEC,seek*1000)
            ok,frame=cap.read()
            if not ok:raise ValueError('cannot sample video at '+str(t))
            h,w=frame.shape[:2]
            if max(w,h)>960:
                factor=960/max(w,h)
                frame=cv2.resize(frame,(round(w*factor),round(h*factor)))
            rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
            r=center_from_rgb(Image.fromarray(rgb))
            fx,fy=r['focal_x'],r['focal_y']
            if previous:
                # No sudden jumps across sampled periods; track movement continuously.
                fx=previous[0]+max(-.2,min(.2,fx-previous[0]))
                fy=previous[1]+max(-.2,min(.2,fy-previous[1]))
            previous=(fx,fy)
            trajectory.append({'t':round(t,3),'fx':round(bounded(fx),4),
                               'fy':round(bounded(fy),4),
                               'confidence':r['confidence'],'method':r['method']})
        return {'track':trajectory,'samples':len(trajectory),'source_duration':round(source_duration,3),
                'mean_focus':{'focal_x':round(sum(x['fx'] for x in trajectory)/len(trajectory),4),
                              'focal_y':round(sum(x['fy'] for x in trajectory)/len(trajectory),4)},
                'method':'LOCAL_FACES_EDGE_SALIENCY_TEMPORAL_SMOOTHING',
                'not_object_identity_or_semantic_scene_verification':True}
    finally:
        cap.release()

def linear_track_expr(points:list[dict],coord:str)->str:
    if not 1<=len(points)<=12 or coord not in ('fx','fy'):
        raise ValueError('bad trajectory')
    vals=[float(p[coord]) for p in points]
    ts=[float(p['t']) for p in points]
    if any(not math.isfinite(x) for x in vals+ts) or any(not 0<=x<=1 for x in vals) or any(ts[i]>=ts[i+1] for i in range(len(ts)-1)):
        raise ValueError('invalid normalized or nonincreasing video focus')
    expr=f'{vals[-1]:.5f}'
    for i in range(len(vals)-2,-1,-1):
        delta=max(.001,ts[i+1]-ts[i])
        interp=f'({vals[i]:.5f}+({vals[i+1]-vals[i]:.5f})*max(0\\,min(1\\,(t-{ts[i]:.4f})/{delta:.4f})))'
        expr=f'if(lt(t\\,{ts[i+1]:.4f})\\,{interp}\\,{expr})'
    return expr

def crop_filter(width:int,height:int,focus:dict)->str:
    if min(width,height)<100:raise ValueError('invalid output dimensions')
    if focus.get('track'):
        fx=linear_track_expr(focus['track'],'fx')
        fy=linear_track_expr(focus['track'],'fy')
    else:
        fx=str(float(focus['focal_x']))
        fy=str(float(focus['focal_y']))
    # Evaluated per video frame after scaling to COVER; never stretch.
    xpos=f'max(0\\,min(iw-ow\\,({fx})*iw-ow/2))'
    ypos=f'max(0\\,min(ih-oh\\,({fy})*ih-oh/2))'
    return (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height}:{xpos}:{ypos},fps=30,format=yuv420p')

def rights_record(scene:dict,approved_media:Path,sha256:str)->dict:
    for key in ('media_path','license_evidence','media_sha256',
                'source_url','author','license_name','attribution'):
        if not isinstance(scene.get(key),str) or not scene[key].strip():
            raise ValueError('Smart Crop licensed media provenance requires '+key)
    if sha256.lower()!=scene['media_sha256'].lower():raise ValueError('licensed source SHA-256 mismatch')
    return {'media_path':scene['media_path'],'source_sha256':sha256,
      'license_evidence':scene['license_evidence'],
      'license_name':scene.get('license_name'),
      'author_or_organization':scene.get('author'),
      'attribution':scene.get('attribution'),
      'source_url':scene.get('source_url'),
      'human_commercial_rights_check_still_required':True,
      'source_exists':approved_media.is_file()}
