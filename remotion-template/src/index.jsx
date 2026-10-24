import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {NewsVideo} from './News';
const initial={stories:[{headline:'DEMO',summary:'Preview only',source:'DEMO',durationFrames:90,media:null}],cues:[],durationFrames:90,category:'TECHNOLOGY',country:'US',demo:true};
const Root=()=> <><Composition id="NewsVertical" component={NewsVideo} durationInFrames={90} fps={30} width={1080} height={1920} defaultProps={initial}/><Composition id="NewsHorizontal" component={NewsVideo} durationInFrames={90} fps={30} width={1920} height={1080} defaultProps={initial}/></>;
registerRoot(Root);
