'use client';

import { useEffect, useRef, useState } from 'react';
import type { BufferGeometry, Material, Mesh, ShaderMaterial, Texture } from 'three';
import styles from './landing.module.css';

const MODEL_URL = 'https://motionsites.org/assets/prompt-media/fa96096e78c8153a70d2.glb';
const vertexShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vEye;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vEye = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;
const fragmentShader = /* glsl */ `
  uniform sampler2D uTexture;
  uniform vec2 uResolution;
  uniform float uBackside;
  uniform float uRefractPower;
  uniform vec3 uAccent;
  varying vec3 vNormal;
  varying vec3 vEye;
  vec3 band(vec2 uv, vec3 ray, float slide, float k) {
    return texture2D(uTexture, clamp(uv + ray.xy * (uRefractPower + slide*k) * 0.5, vec2(0.002), vec2(0.998))).rgb;
  }
  float specular(vec3 light, vec3 n, vec3 eye, float power) {
    vec3 l = normalize(-light);
    return pow(max(dot(n, normalize(l-eye)), 0.0), power);
  }
  void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    vec3 n = normalize(vNormal);
    if (uBackside > 0.5) n = -n;
    vec3 eye = normalize(vEye);
    vec3 rayR = refract(eye,n,1.0/1.15);
    vec3 rayY = refract(eye,n,1.0/1.16);
    vec3 rayG = refract(eye,n,1.0/1.18);
    vec3 rayC = refract(eye,n,1.0/1.22);
    vec3 rayB = refract(eye,n,1.0/1.22);
    vec3 rayP = refract(eye,n,1.0/1.22);
    vec3 color = vec3(0.0);
    for (int i=0; i<SAMPLES; i++) {
      float slide = float(i)/float(SAMPLES)*0.045;
      vec3 tr=band(uv,rayR,slide,1.0), ty=band(uv,rayY,slide,1.0);
      vec3 tg=band(uv,rayG,slide,2.0), tc=band(uv,rayC,slide,2.5);
      vec3 tb=band(uv,rayB,slide,3.0), tp=band(uv,rayP,slide,1.0);
      float r=tr.r*0.5, y=(ty.r*2.0+ty.g*2.0-ty.b)/6.0;
      float g=tg.g*0.5, c=(tc.g*2.0+tc.b*2.0-tc.r)/6.0;
      float b=tb.b*0.5, p=(tp.b*2.0+tp.r*2.0-tp.g)/6.0;
      color += vec3(r+(2.0*p+2.0*y-c)/3.0,g+(2.0*y+2.0*c-p)/3.0,b+(2.0*c+2.0*p-y)/3.0);
    }
    color /= float(SAMPLES);
    color = mix(vec3(dot(color,vec3(0.2125,0.7154,0.0721))),color,1.04);
    float fresnel = pow(clamp(1.0+dot(eye,n),0.0,1.0),5.0);
    vec3 reflection=reflect(eye,n);
    float sky=smoothstep(-0.25,0.65,reflection.y);
    vec3 reflectedLight=mix(vec3(0.20,0.30,0.34),vec3(0.98,1.0,1.0),sky);
    float softbox=pow(max(dot(reflection,normalize(vec3(-0.65,0.35,0.72))),0.0),20.0);
    softbox+=0.7*pow(max(dot(reflection,normalize(vec3(0.8,0.6,-0.3))),0.0),32.0);
    reflectedLight=mix(reflectedLight,vec3(1.0),clamp(softbox,0.0,1.0));
    // Clear faces transmit the registered card; grazing bevels reflect the room.
    float reflectivity=0.035+fresnel*(uBackside>0.5?0.36:0.72);
    color=mix(color,reflectedLight,reflectivity);
    color=mix(color,uAccent,fresnel*0.08);
    float spec=specular(vec3(-1.0,1.0,1.0),n,eye,90.0)+0.6*specular(vec3(1.0,1.0,-1.0),n,eye,54.0);
    color+=mix(vec3(1.0),uAccent,0.10)*spec*(uBackside>0.5?0.10:0.22);
    // Match the template: a transmitted sample replaces the unrefracted DOM line.
    gl_FragColor=vec4(max(color,vec3(0.0)),1.0);
    #include <colorspace_fragment>
  }
`;

/** A local refraction lens over the card border; the surrounding canvas stays clear. */
export function GlassCube({ variant = 'corner' }: { variant?: 'corner' | 'cta' }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stage = stageRef.current!, canvas = canvasRef.current!;
    const cardElement = stage.closest<HTMLElement>('[data-visual-slot="hero"], [data-glass-backdrop]');
    if (!cardElement) return;
    const card: HTMLElement = cardElement;
    const abort = new AbortController();
    const resources = new Set<{dispose(): void}>();
    const own = <T extends {dispose(): void}>(value: T): T => { resources.add(value); return value; };
    const on = (target: EventTarget, event: string, fn: EventListener) => target.addEventListener(event,fn,{signal:abort.signal});
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    let disposed=false, started=false, visible=false, lost=false, raf=0;
    let resizeObserver: ResizeObserver | undefined;
    let sync=()=>{};
    const stop=()=>{cancelAnimationFrame(raf);raf=0;};
    const fail=()=>{lost=true;stop();if(!disposed)setReady(false);};

    async function initialize() {
      if(started||disposed)return;
      started=true;
      try {
        const [THREE,{GLTFLoader},{RoundedBoxGeometry},{mergeVertices,mergeGeometries}]=await Promise.all([
          import('three'),import('three/addons/loaders/GLTFLoader.js'),
          import('three/addons/geometries/RoundedBoxGeometry.js'),import('three/addons/utils/BufferGeometryUtils.js'),
        ]);
        if(disposed)return;
        const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'});
        own({dispose(){renderer.dispose();renderer.forceContextLoss();}});
        renderer.outputColorSpace=THREE.SRGBColorSpace;
        renderer.autoClear=false;
        renderer.setClearColor(0x000000,0);
        const type=renderer.extensions.has('EXT_color_buffer_float')?THREE.HalfFloatType:THREE.UnsignedByteType;
        const rtBack=own(new THREE.WebGLRenderTarget(1,1,{type}));
        const rtFront=own(new THREE.WebGLRenderTarget(1,1,{type}));
        const camera=new THREE.PerspectiveCamera(30,1,0.1,100);camera.position.z=5;
        const scene=new THREE.Scene(),backgroundScene=new THREE.Scene(),backgroundCamera=new THREE.Camera();
        const spinner=new THREE.Group();scene.add(spinner);spinner.rotation.set(-0.42,0.62,0.18);spinner.scale.setScalar(1.5);
        const textureCanvas=document.createElement('canvas');textureCanvas.width=textureCanvas.height=512;
        const ctx=textureCanvas.getContext('2d');if(!ctx)throw new Error('Canvas unavailable');
        const texture=own(new THREE.CanvasTexture(textureCanvas));texture.colorSpace=THREE.SRGBColorSpace;
        texture.minFilter=texture.magFilter=THREE.LinearFilter;texture.generateMipmaps=false;
        const bgMaterial=own(new THREE.ShaderMaterial({
          uniforms:{uTexture:{value:texture}},depthTest:false,depthWrite:false,
          vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}',
          fragmentShader:'uniform sampler2D uTexture; varying vec2 vUv; void main(){gl_FragColor=texture2D(uTexture,vUv);\n#include <colorspace_fragment>\n}',
        }));
        const bg=new THREE.Mesh(own(new THREE.PlaneGeometry(2,2)),bgMaterial);bg.frustumCulled=false;backgroundScene.add(bg);
        // The cube fills more of this local buffer than the template's full-screen buffer.
        const uniforms=(back:boolean)=>({uTexture:{value:back?rtBack.texture:rtFront.texture},uResolution:{value:new THREE.Vector2()},uBackside:{value:back?1:0},uRefractPower:{value:back?0.36:0.54},uAccent:{value:new THREE.Color()}});
        const front=own(new THREE.ShaderMaterial({vertexShader,fragmentShader,uniforms:uniforms(false),defines:{SAMPLES:16},side:THREE.FrontSide}));
        const back=own(new THREE.ShaderMaterial({vertexShader,fragmentShader,uniforms:uniforms(true),defines:{SAMPLES:16},side:THREE.BackSide}));
        const cube:Mesh<BufferGeometry,ShaderMaterial>=new THREE.Mesh(own(new RoundedBoxGeometry(1,1,1,8,0.12)),front);spinner.add(cube);
        canvas.dataset.model='fallback';
        const axisX=new THREE.Vector3(1,0,0),axisY=new THREE.Vector3(0,1,0),q=new THREE.Quaternion();
        let previous=0,pointer:number|null=null,x=0,y=0,pointerTime=0,vx=0,vy=0,released=performance.now()-2000;
        const rotate=(dx:number,dy:number)=>{spinner.quaternion.premultiply(q.setFromAxisAngle(axisY,dx));spinner.quaternion.premultiply(q.setFromAxisAngle(axisX,dy));};
        const draw=()=>{
          if(disposed||lost||!visible||document.hidden)return;
          renderer.setRenderTarget(rtBack);renderer.clear();renderer.render(backgroundScene,backgroundCamera);
          renderer.setRenderTarget(rtFront);renderer.clear();renderer.render(backgroundScene,backgroundCamera);
          cube.material=back;renderer.clearDepth();renderer.render(scene,camera);
          // Only the glass itself reaches the screen. The surrounding canvas stays transparent.
          renderer.setRenderTarget(null);renderer.clear();cube.material=front;renderer.render(scene,camera);
        };
        const tick=(now:number)=>{
          raf=0;if(disposed||lost||!visible||document.hidden)return;
          const dt=Math.min((now-previous)/1000||1/60,0.05);previous=now;
          if(pointer===null&&!motion.matches){
            rotate(vx*dt,vy*dt);const damping=Math.pow(0.94,dt*60);vx*=damping;vy*=damping;
            const idle=Math.min(1,Math.max(0,(now-released-600)/1000));rotate(0.21*dt*idle,0.072*dt*idle);
          }
          draw();if(!motion.matches)raf=requestAnimationFrame(tick);
        };
        sync=()=>{stop();if(disposed||lost||!visible||document.hidden)return;previous=performance.now();if(motion.matches){vx=vy=0;draw();}else raf=requestAnimationFrame(tick);};
        const paintTexture=()=>{
          // Read the real CSS border geometry, including responsive width and radius.
          // This is the template's CanvasTexture backdrop, registered to the actual card.
          const lensRect=stage.getBoundingClientRect(),cardRect=card.getBoundingClientRect();
          const cardStyle=getComputedStyle(card),tokens=getComputedStyle(stage);
          const page=tokens.getPropertyValue('--page').trim()||'#fcfcfa';
          const accent=tokens.getPropertyValue('--accent').trim()||'#4ed7f1';
          front.uniforms.uAccent.value.set(accent);back.uniforms.uAccent.value.set(accent);
          ctx.setTransform(512/lensRect.width,0,0,512/lensRect.height,0,0);
          ctx.clearRect(0,0,lensRect.width,lensRect.height);
          ctx.fillStyle=page;ctx.fillRect(0,0,lensRect.width,lensRect.height);
          const x=cardRect.left-lensRect.left,y=cardRect.top-lensRect.top;
          const border=parseFloat(cardStyle.borderTopWidth)||1;
          const radii=[cardStyle.borderTopLeftRadius,cardStyle.borderTopRightRadius,cardStyle.borderBottomRightRadius,cardStyle.borderBottomLeftRadius].map(value=>Math.max(0,parseFloat(value)-border/2));
          ctx.beginPath();ctx.roundRect(x+border/2,y+border/2,cardRect.width-border,cardRect.height-border,radii);
          ctx.fillStyle=cardStyle.backgroundColor;ctx.fill();
          ctx.strokeStyle=cardStyle.borderTopColor;ctx.lineWidth=border;ctx.stroke();
          texture.needsUpdate=true;
        };
        const layout=()=>{
          const {width,height}=stage.getBoundingClientRect();if(width<1||height<1)return;
          const mobile=matchMedia('(max-width:500px)').matches;renderer.setPixelRatio(Math.min(devicePixelRatio||1,mobile?1.5:2));renderer.setSize(width,height,false);
          const size=renderer.getDrawingBufferSize(new THREE.Vector2());rtBack.setSize(size.x,size.y);rtFront.setSize(size.x,size.y);
          camera.aspect=width/height;camera.updateProjectionMatrix();
          for(const material of [front,back]){material.uniforms.uResolution.value.copy(size);const samples=mobile?8:16;if(material.defines.SAMPLES!==samples){material.defines.SAMPLES=samples;material.needsUpdate=true;}}
          paintTexture();sync();
        };
        resizeObserver=new ResizeObserver(layout);resizeObserver.observe(stage);resizeObserver.observe(card);on(window,'resize',layout);
        on(document.fonts,'loadingdone',layout);void document.fonts.ready.then(()=>{if(!disposed)layout();});
        on(canvas,'pointerdown',((e:PointerEvent)=>{if(!e.isPrimary||e.button!==0||lost)return;pointer=e.pointerId;x=e.clientX;y=e.clientY;pointerTime=e.timeStamp;vx=vy=0;canvas.setPointerCapture(pointer);canvas.dataset.dragging='true';}) as EventListener);
        on(canvas,'pointermove',((e:PointerEvent)=>{if(e.pointerId!==pointer)return;const dx=(e.clientX-x)*.008,dy=(e.clientY-y)*.008,dt=Math.max((e.timeStamp-pointerTime)/1000,1/120);rotate(dx,dy);vx=THREE.MathUtils.clamp(dx/dt,-8,8);vy=THREE.MathUtils.clamp(dy/dt,-8,8);x=e.clientX;y=e.clientY;pointerTime=e.timeStamp;if(motion.matches)draw();}) as EventListener);
        const release=(e:PointerEvent)=>{if(e.pointerId!==pointer)return;if(e.type==='pointercancel'||e.timeStamp-pointerTime>100||motion.matches)vx=vy=0;pointer=null;released=performance.now();canvas.dataset.dragging='false';if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);};
        for(const event of ['pointerup','pointercancel','lostpointercapture'])on(canvas,event,release as EventListener);
        on(canvas,'keydown',((e:KeyboardEvent)=>{const keys:Record<string,[number,number]>={ArrowLeft:[-.16,0],ArrowRight:[.16,0],ArrowUp:[0,-.16],ArrowDown:[0,.16]};if(!keys[e.key]||lost)return;e.preventDefault();vx=vy=0;released=performance.now();rotate(...keys[e.key]);if(motion.matches)draw();}) as EventListener);
        on(canvas,'webglcontextlost',((e:Event)=>{e.preventDefault();fail();}) as EventListener);
        on(document,'visibilitychange',()=>{pointer=null;vx=vy=0;canvas.dataset.dragging='false';sync();});on(motion,'change',sync);
        layout();setReady(true);
        void(async()=>{
          try{
            const response=await fetch(MODEL_URL,{signal:AbortSignal.any([abort.signal,AbortSignal.timeout(12000)])});
            if(!response.ok)throw new Error('Model unavailable');const data=await response.arrayBuffer();if(disposed)return;
            const gltf=await new GLTFLoader().parseAsync(data,MODEL_URL.slice(0,MODEL_URL.lastIndexOf('/')+1));
            const parts:BufferGeometry[]=[];let merged:BufferGeometry|null=null;
            try{
              if(disposed)return;gltf.scene.updateMatrixWorld(true);
              gltf.scene.traverse(object=>{const mesh=object as Mesh;if(!mesh.isMesh)return;const g=mesh.geometry.clone();for(const attribute of Object.keys(g.attributes))if(attribute!=='position')g.deleteAttribute(attribute);const welded=mergeVertices(g,1e-4);g.dispose();welded.computeVertexNormals();welded.applyMatrix4(mesh.matrixWorld);parts.push(welded);});
              if(!parts.length)throw new Error('Empty model');merged=mergeGeometries(parts);if(!merged)throw new Error('Incompatible geometry');merged.computeBoundingBox();
              const size=merged.boundingBox!.getSize(new THREE.Vector3()),largest=Math.max(size.x,size.y,size.z);if(!Number.isFinite(largest)||largest<=0)throw new Error('Invalid geometry');
              merged.center();merged.scale(1/largest,1/largest,1/largest);cube.geometry.dispose();resources.delete(cube.geometry);cube.geometry=own(merged);merged=null;canvas.dataset.model='original';sync();
            }finally{
              merged?.dispose();parts.forEach(g=>g.dispose());
              gltf.scene.traverse(object=>{const mesh=object as Mesh;if(!mesh.isMesh)return;mesh.geometry.dispose();const materials:Material[]=Array.isArray(mesh.material)?mesh.material:[mesh.material];materials.forEach(material=>{Object.values(material).forEach(value=>{if((value as Texture)?.isTexture){(value as Texture).dispose();const image=(value as Texture).image;if(typeof ImageBitmap!=='undefined'&&image instanceof ImageBitmap)image.close();}});material.dispose();});});
            }
          }catch{/* Keep the working rounded glass if the remote GLB is blocked or unavailable. */}
        })();
      }catch{[...resources].reverse().forEach(value=>value.dispose());resources.clear();fail();}
    }
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible&&!started&&!document.hidden)void initialize();else sync();});observer.observe(stage);
    on(document,'visibilitychange',()=>{if(visible&&!started&&!document.hidden)void initialize();});
    return()=>{disposed=true;stop();abort.abort();observer.disconnect();resizeObserver?.disconnect();[...resources].reverse().forEach(value=>value.dispose());resources.clear();sync=()=>{};};
  },[]);

  return <div ref={stageRef} className={variant === 'cta' ? `${styles.iceBadge} ${styles.ctaIceBadge}` : styles.iceBadge}>
    <canvas ref={canvasRef} className={styles.iceCanvas} data-ready={ready} tabIndex={ready?0:-1}
      role="img" aria-label="透明玻璃冰块，折射卡片边线，可拖动或使用方向键旋转。"/>
  </div>;
}
