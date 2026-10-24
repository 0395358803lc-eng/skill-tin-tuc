import React from 'react';
import {AbsoluteFill,Sequence,useCurrentFrame,useVideoConfig,interpolate,Img,OffthreadVideo,staticFile} from 'remotion';

// v0.8.0: original vector-only identities. All words and numbers come from the approved brief.
const fallbackPalettes={
 quick:{navy:'#071624',panel:'#0B2238',accent:'#43D9E8',hot:'#FD694E',text:'#F7FBFF',muted:'#BED3DE'},
 roundup:{navy:'#0A1934',panel:'#132E4E',accent:'#73D8F4',hot:'#EA526F',text:'#F6FAFF',muted:'#BCD1E6'},
 deep_dive:{navy:'#14212D',panel:'#213344',accent:'#EBC36B',hot:'#69BFBE',text:'#FAF9F6',muted:'#C3D0D9'},
};
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
const trimMeta=(v,n=90)=>String(v??'').slice(0,n);
const fade=(f,d=12)=>interpolate(f,[0,d],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
const words=(s)=>Array.from(String(s??'')).length;
const isEnglish=(lang)=>String(lang||'vi-VN').startsWith('en');
const textSizes=(vertical,headline,summary)=>{
 const hl=words(headline),sm=words(summary);
 return {headline:clamp((vertical?76:79)-(Math.max(0,hl-58)*(vertical?.28:.21)),vertical?43:44,vertical?76:79),
 summary:clamp((vertical?33:33)-Math.max(0,sm-150)*.045,vertical?25:25,33)};
};
const profile=(vertical)=>vertical?{
 top:140,left:86,right:126,contentTop:322,contentWidth:858,sourceBottom:190,
 subtitleBottom:385,subtitleMaxHeight:192,captionLeft:90,captionRight:150,
 chartTop:940,chartLeft:78,chartWidth:880,chartMaxHeight:375
}:{
 top:70,left:112,right:120,contentTop:244,contentWidth:850,sourceBottom:70,
 subtitleBottom:166,subtitleMaxHeight:130,captionLeft:235,captionRight:250,
 chartTop:242,chartLeft:1015,chartWidth:792,chartMaxHeight:470
};
const LText=(lang,vi,en)=>isEnglish(lang)?en:vi;
const num=(value)=>Number(value).toLocaleString('en-US',{maximumFractionDigits:1});

function Brand({vertical,theme,lang,styleId,frame}){
 const pos=profile(vertical);
 const label=styleId==='quick'?LText(lang,'TIN NHANH','NEWS FLASH')
    :styleId==='deep_dive'?LText(lang,'PHÂN TÍCH','DEEP DIVE')
    :LText(lang,'BẢN TIN','NEWS ROUNDUP');
 return <div style={{position:'absolute',top:pos.top,left:pos.left,right:pos.right,
    display:'flex',justifyContent:'space-between',alignItems:'center',gap:20,opacity:fade(frame,9)}}>
   <div style={{display:'flex',alignItems:'center',gap:18,minWidth:0}}>
     <div style={{height:vertical?68:62,width:vertical?68:62,display:'flex',
       alignItems:'center',justifyContent:'center',borderRadius:18,
       color:theme.navy,background:theme.accent,fontWeight:900,fontSize:vertical?30:28}}>AN</div>
     <div style={{display:'flex',flexDirection:'column',gap:3}}>
       <div style={{fontWeight:900,color:theme.text,fontSize:vertical?29:30,letterSpacing:2}}>AI NEWS VIDEO</div>
       <div style={{fontSize:vertical?20:19,color:theme.accent,letterSpacing:3,fontWeight:700}}>{label}</div>
     </div>
   </div>
   <div style={{width:vertical?100:180,height:5,borderRadius:9,background:theme.hot}}/>
 </div>;
}

function Infographic({media,frame,vertical,theme,lang}){
 const p=profile(vertical);
 const points=Array.isArray(media?.data_points)?media.data_points:[];
 const compact=vertical&&points.length>=4;
 const fill=clamp((frame-4)/25,0,1);
 return <div style={{position:'absolute',top:p.chartTop,left:p.chartLeft,width:p.chartWidth,
   maxHeight:p.chartMaxHeight,overflow:'hidden',boxSizing:'border-box',
   padding:vertical?(compact?'15px 23px':'22px 29px'):'25px 35px',border:'1px solid '+theme.accent+'77',
   borderRadius:22,background:theme.panel+'EC',boxShadow:'0 14px 42px #02091688',
   color:theme.text}}>
   <div style={{fontSize:vertical?(compact?20:24):22,fontWeight:900,letterSpacing:2,color:theme.accent,marginBottom:compact?7:13}}>
     {LText(lang,'DỮ LIỆU / BIỂU ĐỒ','DATA / INFOGRAPHIC')}
   </div>
   <div style={{fontSize:vertical?(compact?26:34):31,lineHeight:1.2,fontWeight:850,marginBottom:compact?10:17,overflowWrap:'anywhere'}}>
     {String(media?.title||'')}
   </div>
   {points.map((point,i)=>{
     const v=clamp(Number(point.value)||0,0,100);
     return <div key={i} style={{marginBottom:vertical?(compact?8:15):14}}>
       <div style={{display:'flex',justifyContent:'space-between',alignItems:'end',gap:16,fontSize:vertical?(compact?20:25):23,
          fontWeight:750,lineHeight:1.25}}>
         <span style={{overflowWrap:'anywhere',flex:1}}>{point.label}</span>
         <span style={{fontVariantNumeric:'tabular-nums',fontWeight:900,color:theme.accent}}>{num(v)}%</span>
       </div>
       <div style={{background:'#48607880',height:vertical?(compact?8:11):12,marginTop:compact?5:7,borderRadius:8,overflow:'hidden'}}>
         <div style={{width:(v*fill)+'%',height:'100%',background:theme.hot,borderRadius:8}}/>
       </div>
     </div>;
   })}
 </div>;
}

function Background({media,frame,vertical,theme,styleId,lang}){
 const src=media?.asset?staticFile('assets/'+media.asset):null;
 const hasVideo=media?.kind==='video'&&src;
 const hasImage=media?.kind==='image'&&src;
 // A subtle deterministic drift; animation has no media semantics.
 const scale=1+clamp(frame*.00013,0,.045);
 const base={position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',
             transform:'scale('+scale+')',opacity:styleId==='deep_dive'?.46:.58};
 return <AbsoluteFill style={{background:'linear-gradient(132deg,'+theme.navy+','+theme.panel+')'}}>
   {hasVideo?<OffthreadVideo muted src={src} style={base}/>:null}
   {hasImage?<Img src={src} style={base}/>:null}
   <AbsoluteFill style={{background:vertical?
        'linear-gradient(180deg,'+theme.navy+'A0 0%,'+theme.navy+'D9 43%,'+theme.navy+'F6 85%)':
        'linear-gradient(90deg,'+theme.navy+'E8 0%,'+theme.navy+'D9 45%,'+theme.navy+'8A 100%)'}}/>
   <div style={{position:'absolute',width:vertical?680:800,height:vertical?680:800,
     border:'100px solid '+theme.accent+'13',borderRadius:'50%',
     top:-380,right:vertical?-380:-250,pointerEvents:'none'}}/>
   {media?.kind==='infographic'?<Infographic media={media} frame={frame} vertical={vertical} theme={theme} lang={lang}/>:null}
 </AbsoluteFill>;
}

function Caption({cues,frame,vertical,theme}){
 const seconds=frame/30;
 const active=cues.find(c=>seconds>=c.start&&seconds<c.end);
 if(!active)return null;
 const p=profile(vertical),long=words(active.text)>63;
 const fontSize=long?(vertical?38:36):(vertical?46:40);
 const segments=Array.isArray(active.words)?active.words:[];
 return <div style={{position:'absolute',left:p.captionLeft,right:p.captionRight,bottom:p.subtitleBottom,
    textAlign:'center',pointerEvents:'none'}}>
    <span style={{display:'inline-block',maxWidth:'100%',boxSizing:'border-box',
      padding:vertical?'12px 17px':'9px 18px',background:'#030711E8',
      border:'1px solid '+theme.accent+'50',borderRadius:14,
      color:'#FAFDFF',fontWeight:800,fontSize,lineHeight:1.25,overflowWrap:'anywhere',
      textShadow:'0px 2px 3px #000',maxHeight:p.subtitleMaxHeight,overflow:'hidden'}}>
      {segments.length?segments.map((w,i)=><React.Fragment key={i}>
        <span style={{color:seconds>=w.start&&seconds<w.end?'#64D9FF':'#FFFFFF'}}>{w.text}</span>
        {i<segments.length-1?' ':''}
      </React.Fragment>):active.text}
    </span>
 </div>;
}

function Story({story,index,vertical,country,category,demo,frame,theme,styleId,lang,
                isFirst,isLast,introFrames,outroFrames,transitionFrames}){
 const p=profile(vertical);
 const shots=Array.isArray(story.shots)&&story.shots.length?story.shots:[{media:story.media}];
 const n=story.durationFrames||90;
 const shotIdx=clamp(Math.floor(frame/Math.max(1,n)*shots.length),0,shots.length-1);
 const chosen=shots[shotIdx]?.media;
 const transition=Math.max(3,Math.min(transitionFrames||12,Math.floor(n/4)));
 const inAlpha=fade(frame,transition);
 const outAlpha=clamp((n-frame)/transition,0,1);
 const appear=clamp((frame-6)/17,0,1);
 const sizes=textSizes(vertical,story.headline,story.summary);
 const chart=shots.some(x=>x.media?.kind==='infographic');
 const useRightChart=chart&&!vertical;
 const hWidth=useRightChart?820:p.contentWidth;
 // A chart takes the right column: reduce text scale enough that 120–165-char
 // English headlines do not descend into the subtitle or footer safe zone.
 const chartHeadlineSize=useRightChart?clamp(64-Math.max(0,words(story.headline)-52)*.36,35,64):sizes.headline;
 const chartSummarySize=useRightChart?clamp(sizes.summary-3,23,30):sizes.summary;
 const headingMax=useRightChart?300:(vertical?520:440);
 return <AbsoluteFill style={{opacity:Math.min(inAlpha,outAlpha)}}>
   <Background media={chosen} frame={frame} vertical={vertical} theme={theme} styleId={styleId} lang={lang}/>
   <Brand vertical={vertical} theme={theme} lang={lang} styleId={styleId} frame={frame}/>
   <div style={{position:'absolute',left:p.left,top:p.contentTop,width:hWidth,maxWidth:'86%',
     color:theme.text,transform:'translateY('+((1-appear)*28)+'px)',opacity:appear}}>
     <div style={{display:'flex',alignItems:'center',gap:14,marginBottom:vertical?24:18}}>
       <div style={{background:theme.hot,width:vertical?44:36,height:6,borderRadius:20}}/>
       <span style={{letterSpacing:3,fontSize:vertical?25:23,fontWeight:850,color:theme.accent}}>
          {LText(lang,'TIN SỐ ','STORY ')}{String(index+1).padStart(2,'0')}
       </span>
     </div>
     <div style={{fontSize:chartHeadlineSize,fontWeight:900,lineHeight:useRightChart?1.1:1.15,letterSpacing:-.6,
       maxHeight:headingMax,overflowWrap:'anywhere',textShadow:'0 3px 17px #020916',
       marginBottom:vertical?23:20}}>
       {story.headline}
     </div>
     <div style={{width:vertical?130:150,height:6,borderRadius:9,background:theme.hot,marginBottom:vertical?24:20}}/>
     <div style={{fontSize:chartSummarySize,lineHeight:1.32,color:theme.text,opacity:.92,
       overflowWrap:'anywhere',maxWidth:vertical?820:810}}>
       {story.summary}
     </div>
   </div>
   <div style={{position:'absolute',left:p.left,right:p.right,bottom:p.sourceBottom,
     borderTop:'1px solid '+theme.accent+'42',paddingTop:13,display:'flex',gap:25,
     justifyContent:'space-between',alignItems:'center',
     color:theme.muted,fontSize:vertical?23:21,fontWeight:700}}>
      <span style={{maxWidth:vertical?'72%':'76%',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
         {LText(lang,'NGUỒN','SOURCE')}: {trimMeta(story.source,84)}
      </span>
      <span style={{fontWeight:900,color:theme.accent,letterSpacing:2}}>AI NEWS</span>
   </div>
   {isFirst&&frame<introFrames?<div style={{position:'absolute',top:vertical?228:147,right:vertical?120:136,
      color:theme.accent,fontWeight:950,letterSpacing:3,fontSize:vertical?25:22,opacity:1-frame/introFrames}}>
     {LText(lang,'BẮT ĐẦU BẢN TIN','START OF BRIEF')}
   </div>:null}
   {isLast&&n-frame<=outroFrames?<div style={{position:'absolute',top:vertical?235:148,right:vertical?124:140,
      color:theme.accent,fontWeight:950,letterSpacing:2,fontSize:vertical?23:22,
      opacity:clamp((outroFrames-(n-frame))/Math.max(1,outroFrames),0,1)}}>
     {LText(lang,'KẾT THÚC BẢN TIN','END OF BRIEF')}
   </div>:null}
   {demo?<div style={{position:'absolute',left:'7%',right:'7%',bottom:vertical?58:16,
      textAlign:'center',padding:vertical?11:7,borderRadius:12,fontSize:vertical?30:22,
      fontWeight:900,color:'#FFFFFF',background:'#B51D35F2',letterSpacing:1}}>
      {LText(lang,'DEMO • KHÔNG PHẢI TIN THẬT','DEMO • NOT REAL NEWS')}
   </div>:null}
 </AbsoluteFill>;
}

export const NewsVideo=(props)=>{
 const frame=useCurrentFrame(),{width}=useVideoConfig(),vertical=width<1200;
 const styleId=['quick','roundup','deep_dive'].includes(props.visualStyle)?props.visualStyle:'roundup';
 const theme=fallbackPalettes[styleId];
 const stories=Array.isArray(props.stories)?props.stories:[];
 const lang=props.language||'vi-VN';
 let cursor=0;
 return <AbsoluteFill style={{background:theme.navy,fontFamily:'Arial, "Segoe UI", sans-serif'}}>
   {stories.map((story,i)=>{
      const start=cursor;
      const duration=Math.max(1,story.durationFrames||90);
      cursor+=duration;
      return <Sequence key={i} from={start} durationInFrames={duration}>
         <Story story={story} index={i} vertical={vertical}
           country={props.country} category={props.category} demo={props.demo===true}
           frame={frame-start} theme={theme} styleId={styleId} lang={lang}
           isFirst={i===0} isLast={i===stories.length-1}
           introFrames={props.introFrames||12} outroFrames={props.outroFrames||12}
           transitionFrames={props.transitionFrames||12}/>
      </Sequence>;
   })}
   <Caption cues={props.cues||[]} frame={frame} vertical={vertical} theme={theme}/>
   <div style={{position:'absolute',top:0,left:0,
      width:(clamp(frame/Math.max(1,props.durationFrames||cursor),0,1)*100)+'%',
      height:vertical?9:7,background:theme.hot}}/>
 </AbsoluteFill>;
};
