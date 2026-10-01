/* 블로그 자동 임시저장 - 화면 로직
   꾸밈/해시태그 규칙과 미리보기 렌더링은 기존 "블로그 원고 서식 도구" 페이지의 로직을 그대로 옮겨왔다. */
"use strict";
var $=function(i){return document.getElementById(i)};
var F=["mode","bs","lh","ba","kc","kc2","use2","hl","qs","qon","qch","deco","kw","swid","note","memo"];

/* ---------- 서버 통신 ---------- */
async function api(path,body){
  var opt=body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-App":"1"},body:JSON.stringify(body)};
  var r=await fetch(path,opt);
  var d={};try{d=await r.json()}catch(e){}
  if(!r.ok)throw new Error(d.error||("오류 "+r.status));
  return d;
}
/* 기존 페이지의 sample.json(prompt) 자리에 Gemini 호출을 연결 */
var sample={json:async function(prompt){var d=await api("/api/ai",{prompt:prompt});return d.result||{}}};

var SWATCHES=[
  {id:"red",name:"빨간계열",kc:"#eb1600",kc2:"#e0765f",hl:"#ffd4cc"},
  {id:"blue",name:"파란계열",kc:"#005aca",kc2:"#5b8fc7",hl:"#cce7ff"},
  {id:"green",name:"초록계열",kc:"#00803a",kc2:"#5fa77c",hl:"#ccffdc"},
  {id:"brown",name:"갈색계열",kc:"#b85200",kc2:"#b98457",hl:"#ffe8cc"},
  {id:"purple",name:"보라계열",kc:"#6400cc",kc2:"#9678b6",hl:"#e7ccff"},
  {id:"pink",name:"핑크계열",kc:"#e70051",kc2:"#e88ba9",hl:"#ffccde"}
];
function renderSwatches(){
  var box=$("swatches");if(!box)return;
  var cur=$("swid").value;
  box.innerHTML="";
  SWATCHES.forEach(function(s){
    var row=document.createElement("label");
    row.className="swatch"+(cur===s.id?" on":"");
    row.innerHTML='<input type="checkbox"'+(cur===s.id?" checked":"")+'><span class="dots"><span class="dot" style="background:'+s.kc+'"></span><span class="dot" style="background:'+s.hl+'"></span><span class="dot" style="background:'+s.kc2+'"></span></span><span class="hexrow"><span>'+s.kc+'</span><span>'+s.hl+'</span><span>'+s.kc2+'</span></span>';
    row.querySelectorAll(".hexrow span").forEach(function(sp){
      sp.addEventListener("click",function(e){
        e.preventDefault();e.stopPropagation();
        copyText(sp.textContent);
        var old=sp.textContent;sp.textContent="복사됨";sp.classList.add("copied");
        setTimeout(function(){sp.textContent=old;sp.classList.remove("copied")},900);
      });
    });
    row.querySelector("input").addEventListener("change",function(){
      if(this.checked){
        $("swid").value=s.id;
        $("kc").value=s.kc;$("hl").value=s.hl;$("kc2").value=s.kc2;$("use2").checked=false;
      }else{
        $("swid").value="";
      }
      render();
    });
    box.appendChild(row);
  });
}
function applyQuoteMarkers(body){
  var chars=((CUR.qch||"")||"").split(",").map(function(s){return s.trim()}).filter(Boolean);
  if(!!!CUR.qon||!chars.length)return body;
  var escRe=function(s){return s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")};
  var re=new RegExp("^(?:"+chars.map(escRe).join("|")+")\\s?");
  return body.map(function(t){
    if(t.indexOf("Q|")===0||t.indexOf("C|")===0||t.indexOf("H|")===0)return t;
    if(re.test(t))return "C|"+t.replace(re,"");
    return t;
  });
}
function sentenceGroups(body){
  var groups=[],cur=[];
  body.forEach(function(raw,pos){
    var t=raw.replace(/^(?:Q\||H\||U\||C\|)+/,"");
    if(!t){if(cur.length){groups.push(cur);cur=[]}return}
    if(NUM.test(t)){if(cur.length){groups.push(cur);cur=[]}return}
    cur.push(pos);
    if(/[.?!][)"'”』」]*\s*$/.test(t.trim())){groups.push(cur);cur=[]}
  });
  if(cur.length)groups.push(cur);
  return groups;
}
function unifySentenceStyles(body){
  var groups=sentenceGroups(body);
  groups.forEach(function(idxs){
    var count={b:0,u:0},re=/\{([bu]):[^{}]*\}/g;
    idxs.forEach(function(pos){var m;while((m=re.exec(body[pos]))){count[m[1]]++}});
    if(count.b>0&&count.u>0){
      var winner=count.b>=count.u?"b":"u";
      idxs.forEach(function(pos){
        body[pos]=body[pos].replace(/\{([bu]):([^{}]*)\}/g,function(m0,tg,c){return "{"+winner+":"+c+"}"});
      });
    }
  });
  return body;
}
function applyTableMarker(body){
  if(!!!CUR.qon)return body;
  var out=body.slice();
  for(var i=0;i<out.length;i++){
    if(out[i].indexOf("(표)")===-1)continue;
    for(var j=i+1;j<out.length;j++){
      if(!out[j])continue;
      if(NUM.test(out[j]))break;
      if(out[j].indexOf("Q|")!==0)out[j]="Q|"+out[j];
      break;
    }
  }
  return out;
}
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
var NUM=/^\d+(\.\d+)*\.?(\s*,\s*\d+(\.\d+)*\.?)*$/;

/* ---------- 원고 나누기 (기존 split과 같은 규칙) ---------- */
function splitText(text){
  var L=(text||"").split("\n").map(function(s){return s.trim()});
  var i=L.findIndex(function(t){return NUM.test(t)});
  if(i<0)i=0;
  return{meta:L.slice(0,i).filter(Boolean),body:L.slice(i)};
}
function stripMarks(s){return(s||"").replace(/\{[a-z]+:([^{}]*)\}/g,"$1").trim()}
/* 글 제목: 상단 정보에서 '제목'으로 시작하는 줄 → 없으면 '키워드' 아닌 첫 줄 → 없으면 파일 이름 */
function guessTitle(meta,fname){
  var clean=meta.map(stripMarks).filter(Boolean);
  for(var i=0;i<clean.length;i++){var m=clean[i].match(/^\[?\s*(?:제목|타이틀|title)\s*\]?\s*[:：]?\s*(.+)$/i);if(m&&m[1].trim())return m[1].trim()}
  var c=clean.find(function(t){return !/^\[?\s*(키워드|태그|해시태그|keyword)/i.test(t)&&!/^#/.test(t)});
  if(c)return c.replace(/^[:：\-\s]+/,"");
  return(fname||"제목 없음").replace(/\.(hwpx|txt)$/i,"");
}

/* ---------- 미리보기 HTML (기존 render의 "블로그" 형식 부분) ---------- */
function renderHTML(c,body,lastTags){
  var h="",sp={body:body.slice()};
  if(!c.qon){sp.body=sp.body.map(function(t){return(t.indexOf("Q|")===0||t.indexOf("C|")===0)?t.slice(2):t})}
  var lhv=parseFloat(c.lh)||180;if(lhv>=10)lhv=lhv/100;  // 180 → 1.8, 1.8 → 1.8
  var tc="#000000";
  var P="margin:0 0 6px;font-size:"+c.bs+"px;line-height:"+lhv+";color:"+tc+";text-align:"+c.ba+";";
    var qc="#666666",qm="#c4c4c4";
    var KW=c.kw.split(",").map(function(s){return s.trim()}).filter(Boolean).sort(function(a,b){return b.length-a.length});
    var mk=function(x){return '<p style="margin:14px 0 0;font-size:46px;line-height:1;text-align:center;color:'+qm+';font-family:Georgia,serif;">'+x+'</p>'};
    var styleSet=[{kc:c.kc}];
    if(c.use2)styleSet.push({kc:c.kc2});
    var styleTurn=0;
    var wrapStyle=function(k,x){
      if(k==="u")return '<span style="text-decoration:underline;text-underline-offset:3px;">'+x+'</span>';
      var s=styleSet[styleTurn%styleSet.length];styleTurn++;
      if(k==="bu")return '<span style="text-decoration:underline;text-underline-offset:3px;color:'+s.kc+';font-weight:bold;">'+x+'</span>';
      return '<span style="color:'+s.kc+';font-weight:bold;">'+x+'</span>';
    };
    var stripLead=function(s){return s.replace(/^(?:Q\||H\||C\|)+/,"")};
    var unwrapStray=function(s){
      var out=s,guard=0;
      while(/\{[a-z]+:[^{}]*\}/.test(out)&&guard<5){out=out.replace(/\{[a-z]+:([^{}]*)\}/g,"$1");guard++}
      return out;
    };
    var kwColorize=function(escapedText){
      var x=escapedText;
      KW.forEach(function(k){x=x.split(esc(k)).join("{r:"+esc(k)+"}")});
      return x.replace(/\{r:([^{}]*)\}/g,function(m,y){return wrapStyle("r",unwrapStray(y))});
    };
    var applyKW=function(raw){return kwColorize(esc(raw))};
    var accent=function(t){
      t=esc(t);
      var TAGRE=/\{(bu|b|u):([^{}]*)\}/g,segs=[],last=0,mm;
      while((mm=TAGRE.exec(t))){segs.push([null,t.slice(last,mm.index)]);segs.push([mm[1],mm[2]]);last=TAGRE.lastIndex}
      segs.push([null,t.slice(last)]);
      var out=segs.map(function(seg){
        if(seg[0])return wrapStyle(seg[0],unwrapStray(seg[1]));
        return kwColorize(seg[1]);
      }).join("");
      return unwrapStray(out);
    };
    var PB=P.replace("margin:0 0 6px;","margin:0;");
    var q=[],cq=[];
    var flush=function(){
      if(!q.length)return;
      var lines=q.slice();
      lines[0]=lines[0].replace(/^["“”']+\s*/,"");
      lines[lines.length-1]=lines[lines.length-1].replace(/\s*["“”']+$/,"");
      lines.forEach(function(t,i){
        var mt=i===0?"16px":"0",mb=i===lines.length-1?"16px":"0";
        h+='<p style="margin:'+mt+' 0 '+mb+';font-size:'+c.qs+'px;line-height:1.8;text-align:center;font-style:italic;color:'+qc+';">'+applyKW(t)+'</p>';
      });
      q=[];
    };
    var flushC=function(){
      if(!cq.length)return;
      var bsz=parseInt(c.bs,10)+2;
      cq.forEach(function(t,i){
        var first=i===0,last=i===cq.length-1;
        var bd="border-left:2px solid #000000;border-right:2px solid #000000;"+(first?"border-top:2px solid #000000;":"")+(last?"border-bottom:2px solid #000000;":"");
        var padTop=first?"16px":"4px",padBot=last?"16px":"4px";
        h+='<p style="margin:'+(first?"16px":"0")+' 0 '+(last?"16px":"0")+';'+bd+'padding:'+padTop+' 16px '+padBot+';font-size:'+bsz+'px;line-height:1.5;text-align:center;font-weight:bold;">'+applyKW(t)+'</p>';
      });
      cq=[];
    };
    sp.body.forEach(function(t){
      if(t.indexOf("Q|")===0){flushC();q.push(unwrapStray(stripLead(t.slice(2))));return}
      if(t.indexOf("C|")===0){flush();cq.push(unwrapStray(stripLead(t.slice(2))));return}
      flush();flushC();
      if(!t){h+='<p style="'+PB+'">&nbsp;</p>';return}
      if(NUM.test(t)){h+='<p style="'+PB+'margin-top:30px;">'+esc(t)+'</p>';return}
      if(t.indexOf("H|")===0){h+='<p style="'+PB+'"><span style="background-color:'+c.hl+';padding:2px 4px;">'+esc(unwrapStray(stripLead(t.slice(2))))+'</span></p>';return}
      if(t.indexOf("U|")===0)t=t.slice(2);
      h+='<p style="'+PB+'">'+accent(t)+'</p>';
    });
    flush();flushC();
  if(lastTags&&lastTags.length){
    h+='<p style="margin:28px 0 0;font-size:'+c.bs+'px;line-height:1.6;color:#000000;text-align:'+c.ba+';">'+lastTags.map(function(t){return "#"+esc(t)}).join(" ")+'</p>';
  }
  return '<div style="text-align:'+c.ba+'">'+h+'</div>';
}

/* ---------- AI 꾸밈 (기존 페이지의 지시문 그대로) ---------- */
async function aiMarks(sp){
  var idxMap=[],numbered=[];
  sp.body.forEach(function(t,pos){if(t){idxMap.push(pos);numbered.push(idxMap.length-1+": "+t)}});
  var decoRule={
    low:"- 이번 원고는 꾸밈 정도를 낮게 한다. 기준: 아래에서 정의한 '단락' 하나하나마다 반드시 최소 1문장은 꾸며야 한다 — bold(글자색+굵게), 밑줄, 배경색(H) 중 아무거나 하나를 골라 그 단락에서 가장 중요한 문장 1개에 적용해라. 절대 0개로 비워두면 안 된다(사진 자리표시 줄만 있는 단락은 예외). 단, 그 1개를 넘어서 욕심내지 말고 딱 1문장만 — 합쳐서 단락당 총 1개(아주 가끔 눈에 띄게 중요한 단락이면 2개까지만)로 제한한다. 배경색(H)은 단락 전체를 통틀어 아주 가끔만 쓰고, bold나 밑줄을 더 자주 선택해라. 인용구(Q)는 특별히 임팩트 있는 단락에만 가끔 추가한다.",
    mid:"- 이번 원고는 꾸밈 정도를 보통으로 한다. 기준: 아래에서 정의한 '단락' 하나하나마다 배경색(H) 바꾸는 문장 1개, 밑줄 처리하는 문장 1개, 폰트컬러+bold 처리(키워드나 문장) 1~2개 — 합쳐서 총 3~4개 정도 넣는다. 배경색(H)은 딱 1문장만 쓰고 절대 더 늘리지 마라 — 배경색만 여러 개 쓰는 게 제일 안 좋은 패턴이다. 인용구(Q)는 단락마다 있으면 좋지만 필수는 아니다.",
    high:"- 이번 원고는 꾸밈 정도를 최대한 높게 한다. 기준: 아래에서 정의한 '단락' 하나하나마다 배경색(H) 바꾸는 문장 2개, 밑줄 처리하는 문장 1개, 폰트컬러+bold 처리(키워드나 문장) 2개 — 반드시 합쳐서 총 5개를 그 단락 안에 넣는다. 이건 목표치가 아니라 필수 개수다: 원고에 있는 단락 하나하나마다 정확히 이 5개(배경 2 + 밑줄 1 + bold 2)를 채워야 하고, 특정 단락만 적게 넣거나 건너뛰면 안 된다. 배경색(H)을 2문장보다 많이 쓰지는 말고, 밑줄도 1문장만. 인용구(Q)는 단락마다 가능하면 하나씩 추가로 넣는다(위 5개와는 별개)."
  }[(CUR.deco||"mid")]||"";
  var noteVal=((CUR.note||"")||"").trim();
  var noteRuleTop=noteVal?"\n- ⚠️ 클라이언트 전용 특이사항(다른 모든 규칙보다 최우선): "+noteVal+" — 이 특이사항에 적힌 범위·기준·개수(예: \"문장 1개\", \"~까지만\")는 정확한 지시이니 그대로 따르고, 절대 임의로 늘리거나 줄이지 마라. 예를 들어 특이사항이 \"문장 1개\"라고 했는데 2개 이상을 고르면 틀린 것이다. 아래에 나오는 단락 정의, 개수 기준, 인용구 선택 방식 등 다른 규칙들은 이 특이사항이 다루지 않는 부분에서만 참고하고, 이 특이사항과 충돌하는 부분은 전부 무시해라.":"";
  var noteRuleBottom=noteVal?"\n- 마지막으로 다시 한번: 위에서 준 클라이언트 특이사항(\""+noteVal+"\")의 범위·개수 지시를 지켰는지 스스로 점검해라. 특이사항이 정한 것보다 더 많이/적게 고르지 않았는지 반드시 재확인해라.":"";
  var noQuote=!!!CUR.qon;
  var quoteNote=noQuote?"\n- 이번 원고는 인용구(Q) 기능을 쓰지 않는다. marks에는 절대 \"Q\" 타입을 넣지 마라(사용 가능한 타입은 \"H\"뿐이다). 원래 인용구로 고를 만큼 임팩트 있던 문장이 있으면, 대신 배경색(H)이나 bold/underline으로 강조해서 그 부분이 묻히지 않게 해라.":"";
  var prompt="다음은 블로그 원고를 줄 단위로 나눈 목록이다(번호: 내용). 원문은 절대 고치지 말고, 어떤 줄/문구에 어떤 표시를 붙일지만 정해서 JSON으로만 답하라. 설명이나 코드블록 없이 JSON 객체 하나만 출력해라.\n서식은 4종류이고 같은 줄/문구에 절대 겹치면 안 된다: 1) 인용구, 2) 배경색만(글자 스타일은 그대로), 3) 글자색+굵게, 4) 밑줄. 특히 배경색(H)과 글자색+굵게(bold)는 절대로 같은 문장이나 구절에 동시에 적용되면 안 된다 — 반드시 서로 다른 문장에 각각 하나씩만 적용해라.\n- 전체 원고에서 배경색(H)만 계속 반복해서 고르지 마라. bold와 밑줄(underline)도 배경색만큼, 혹은 그보다 더 많이 사용해서 서식 종류를 다양하게 섞어야 한다. 배경색이 절반을 넘게 쓰이면 안 된다.\n- 꾸밀 곳을 고를 때는 항상 문장 단위로 판단해라(여기서 \"문장\"은 줄바꿈이 아니라 마침표.물음표.느낌표로 끝나는 실제 문장을 뜻한다 — 아래에서 더 자세히 설명한다). 단락 전체를 보고 대표 문장 한두 개만 고르는 게 아니라, 그 단락에 있는 문장들을 처음부터 끝까지 하나씩 순서대로 짚어가면서 \"이 문장을 꾸밀까, 어떤 스타일로 꾸밀까\"를 각각 정해야 한다. 아래 꾸밈 정도별 목표 개수는 이렇게 문장 단위로 훑어야만 채울 수 있는 양이니, 단락을 훑지 않고 대충 몇 개만 고르지 마라.\n형식: {\"marks\":[{\"i\":줄번호,\"t\":\"Q\"|\"H\"}],\"bold\":[\"강조할 문구\",...],\"underline\":[\"밑줄 칠 문구\",...]}\n규칙:"+noteRuleTop+"\n- '단락(문단)'의 정의: 원고에서 완전히 빈 줄(내용이 하나도 없는 줄)로 나뉘는 덩어리 하나가 '한 단락'이다. 원고 맨 앞의 \"0\"이나 맨 뒤의 \"56\"처럼 숫자만 있는 줄이 어쩌다 하나씩 보이더라도, 그걸 기준으로 단락을 나누지 마라 — 이 원고들은 번호가 거의 없거나 듬성듬성 있을 수 있고, 실제 단락 구분은 오직 빈 줄이다. 즉 원고 전체에서 빈 줄과 빈 줄 사이에 있는 연속된 텍스트 줄들을 각각 하나의 독립된 단락으로 보고, 그 단락 하나하나마다 아래 꾸밈 정도 기준 개수를 채워야 한다. 원고 전체를 하나의 큰 덩어리로 보고 개수를 몰아서 채우면 절대 안 되고, 빈 줄로 나뉜 짧은 단락 하나하나에 각각 따로 채워야 한다.\n- 가장 중요한 원칙: 줄바꿈을 문장이 끝났다는 신호로 착각하지 마라. 문장이 끝났는지는 오직 마침표(.)·물음표(?)·느낌표(!) 같은 문장부호로만 판단한다. 어떤 줄이 이런 문장부호 없이 끝나 있으면, 그 문장은 다음 줄(들)로 계속 이어지는 것이다. 전체 원고를 먼저 흐름대로 읽으면서 어디서부터 어디까지가 실제로 하나의 문장인지(마침표 기준) 파악한 다음에, 그 단위로 꾸밀 곳과 문장 개수를 판단해라. 줄 단위를 문장 단위로 착각하면 개수 계산도, 문장 중간을 끊어 꾸미는 것도 전부 틀리게 된다.\n- 원문은 한 문장이 여러 줄로 개행되어 있는 경우가 매우 많다(예: \"방문과 문틀도\" 다음 줄에 \"집의 분위기에 생각보다 큰 영향을 줍니다.\"가 오면 이 두 줄은 사실 한 문장이다). 인용구(Q)나 배경색(H)으로 고를 때는 반드시 그 문장(또는 이어지는 여러 문장)에 속한 줄 전체를 처음부터 끝까지 빠짐없이 포함해라. 문장 중간에서 끊거나 한 문장의 일부 줄만 고르지 마라.\n- bold/underline도 마찬가지다. 절대로 문장의 마지막 줄이나 일부 조각(예: \"있습니다.\", \"발생할 수 있습니다.\" 같은 짧은 꼬리 부분)만 골라서 꾸미면 안 된다. 반드시 그 문장이 시작하는 줄부터 끝나는 줄까지 전부 찾아서 bold나 underline 배열에 각 줄의 전체 텍스트를 하나씩 전부 넣어라. 예를 들어 원문이 다음처럼 4줄에 걸쳐 있다면(\"이외에도\" / \"수입인지와\" / \"중개수수료 등이\" / \"별도로 발생할 수 있습니다.\") 이 문장을 밑줄로 꾸미기로 했다면 underline 배열에 \"이외에도\", \"수입인지와\", \"중개수수료 등이\", \"별도로 발생할 수 있습니다.\" 이렇게 4개 항목을 전부 넣어야 한다. 마지막 줄 하나만 넣고 앞의 세 줄을 빠뜨리는 것은 완전히 틀린 것이다.\n"+quoteNote+"\n- 여러 줄에 걸쳐 이어지는 한 문장을 꾸밀 때는, 쉼표로 여러 항목이 나열되다가 하나의 술어로 끝나는 문장(예: \"A와 B, C까지 함께 살펴보는 것이 중요합니다\"처럼 결국 하나의 흐름/하나의 주장인 문장)이면 절대로 항목마다 다른 색을 칠하지 마라. 그런 문장은 처음부터 끝까지 전체를 하나의 구절로 보고 스타일 하나만 통일해서 적용해라(그 문장에 속한 모든 줄을 bold나 underline 목록에 각각 같은 스타일로 넣으면 된다). 한 문장 안에서 앞부분엔 배경색, 뒷부분엔 밑줄처럼 서로 다른 스타일을 섞어 칠하는 것은 절대 하지 마라 — 이렇게 하면 원고가 지저분해 보인다.\n- 정말로 서로 독립적인 두 문장이 원문 상 한 줄에 붙어 있는 경우(예: \"그렇습니다. 이건 별도로 확인이 필요합니다.\"처럼 마침표로 명확히 나뉘는 두 문장이 한 줄에 있는 경우)에만 그 줄 안에서 각 문장에 서로 다른 스타일을 따로 적용할 수 있다. 이 경우를 제외하면 한 문장 = 스타일 하나로 원칙을 지켜라.\n- bold와 underline은 단어 한두 개짜리 짧은 토막이 아니라, 의미가 통하는 구(句) 단위나 문장 전체 길이로 고른다. 대략 8~25자 정도의 자연스러운 구절 단위로 고르는 걸 기본으로 하고, 문장 전체를 강조하는 것도 괜찮다.\n"+decoRule+"\n- bold와 underline은 t가 없는(Q도 H도 아닌) 일반 줄에 나오는 구절만 고른다. Q나 H로 고른 줄의 구절은 절대 bold나 underline에 넣지 마라.\n- 다음 단어는 이미 자동으로 색이 입혀지므로 그 단어 자체를 bold나 underline 문구로 통째로 고르지는 마라: "+((CUR.kw||"")||"없음")+". 하지만 이 단어가 들어있는 문장이나 줄이라고 해서 나머지 부분까지 꾸미지 않고 건너뛰면 안 된다 — 그 단어를 뺀 나머지 부분, 또는 다른 문장은 평소처럼 적극적으로 bold/underline/인용구/배경색으로 꾸며라. 자동 강조 단어의 존재가 전체 꾸밈 개수(단락당 목표치)를 줄이는 이유가 되면 안 된다.\n- 매우 중요: 위에서 정의한 단락(빈 줄로 구분된 덩어리)을 원고 처음부터 끝까지 하나도 빠짐없이 전부 살펴봐라. 특정 단락 하나를 통째로 건너뛰고 꾸밈이 하나도 없이 남겨두는 일이 있으면 안 된다. 각 단락마다 위 꾸밈 정도 기준 개수를 채웠는지 스스로 확인한 다음 다음 단락으로 넘어가라. 원고가 길어서 단락이 10개, 20개가 넘어가더라도 예외 없이 전부 다 확인해라.\n- \"[사진 26~34]\"처럼 대괄호로 된 사진/이미지 자리 표시 줄은 그 자체로 하나의 짧은 '단락'(앞뒤가 빈 줄로 둘러싸인 덩어리)을 이루는 경우가 많다. 이런 사진 표시 줄만 있는 단락은 꾸밀 실제 문장이 없으니 건너뛰어도 된다(개수에서 제외). 그 대신 바로 앞 단락과 바로 뒤 단락은 각각 독립된 단락이니, 사진 표시 줄이 있다고 앞뒤 단락을 하나로 합치거나 개수를 줄이지 말고 각각 정상적으로 목표 개수를 채워라."+noteRuleBottom+"\n\n줄 목록:\n"+numbered.join("\n");
  if(sp.meta&&sp.meta.length){prompt+="\n\n(참고용 원고 상단 정보 — 꾸밀 줄 목록에는 포함되지 않지만 특이사항이 이 부분을 언급하면 참고해라)\n"+sp.meta.map(stripMarks).join("\n")}
      var d=await sample.json(prompt,{cache:false,modelTier:"complex"});
      var newBody=sp.body.slice(),marked={};
      newBody.forEach(function(t,pos){if(t.indexOf("Q|")===0||t.indexOf("C|")===0)marked[pos]=true});
      (d.marks||[]).forEach(function(mk){
        var pos=idxMap[mk.i];if(pos===undefined||marked[pos])return;
        var pre=mk.t==="Q"?"Q|":mk.t==="H"?"H|":"";
        if(pre){newBody[pos]=pre+newBody[pos];marked[pos]=true}
      });
      function findFreeSpot(line,ph){
        var from=0;
        while(true){
          var idx=line.indexOf(ph,from);
          if(idx<0)return -1;
          var overlaps=false,re=/\{[a-z]+:[^{}]*\}/g,m;
          while((m=re.exec(line))){
            var s=m.index,e=s+m[0].length;
            if(idx<e&&(idx+ph.length)>s){overlaps=true;break}
          }
          if(!overlaps)return idx;
          from=idx+1;
        }
      }
      function applyPhrases(list,tag){
        (list||[]).forEach(function(ph){
          ph=(ph||"").trim();if(!ph)return;
          var done=false;
          newBody=newBody.map(function(line,pos){
            if(done||marked[pos])return line;
            var idx=findFreeSpot(line,ph);
            if(idx<0)return line;
            done=true;
            return line.slice(0,idx)+"{"+tag+":"+ph+"}"+line.slice(idx+ph.length);
          });
        });
      }
      applyPhrases(d.bold,"b");
      applyPhrases(d.underline,"u");
      newBody=unifySentenceStyles(newBody);
  return newBody;
}

function extractExistingTags(text){
  var m=(text||"").match(/#[^\s#]+/g)||[];
  var seen={},out=[];
  m.forEach(function(x){
    var t=x.replace(/^#+/,"").replace(/[,.!?~…"'“”()\[\]]+$/,"").trim();
    if(!t||seen[t])return;
    seen[t]=true;out.push(t);
  });
  return out.length>=3?out:[];
}
async function generateTags(sample,sp,noteVal){
  var text=(sp.meta.join("\n")+"\n"+sp.body.join("\n")).trim();
  if(!text)return[];
  noteVal=(noteVal||"").trim();
  var noteRule=noteVal?"\n⚠️ 클라이언트 특이사항(다른 모든 규칙보다 최우선): "+noteVal+" — 여기에 해시태그 개수, 조합 방식, 지역/동네 목록, 구체적인 태그 목록 등이 적혀 있으면 그 지시를 반드시 그대로 따르고 절대 빠뜨리지 마라. 예를 들어 여러 동네 이름을 나열하며 각 동네마다 여러 업종 조합을 만들라고 했다면, 나열된 동네 전부에 대해 빠짐없이 조합을 만들어야 한다. 이 경우 아래 '10개' 관련 기본 규칙은 무시하고 특이사항에서 요구하는 만큼(수십 개가 되어도) 전부 만들어라.\n":"";
  var prompt="다음은 블로그 원고(제목/키워드+본문)이다. 이 원고를 분석해서 네이버 블로그 SEO(검색엔진 최적화)와 GEO(생성형 AI 검색·지역 노출)에 도움이 될 해시태그를 골라라. 설명이나 코드블록 없이 JSON 객체 하나만 출력해라.\n형식: {\"tags\":[\"태그1\",\"태그2\",...]}\n규칙:"+noteRule+"- # 기호는 붙이지 말고 태그 단어/구절만 담아라.\n- 각 태그는 띄어쓰기 없이 붙여써라(예: \"강남필름시공\").\n- 실제 사람들이 검색창에 칠 법한 자연스러운 키워드/구절이어야 한다. 너무 포괄적이거나 뭉뚱그린 단어 하나만 있는 태그(예: \"인테리어\",\"정보\",\"블로그\")는 피하고, 구체적인 구절로 만들어라.\n- 원고에 지역명(동·구·시 등)이 등장하면, '지역명+업종' 또는 '지역명+서비스명' 조합 태그를 최소 2~3개는 반드시 포함해라(예: \"○○동인테리어\",\"○○구필름시공\") — 이게 GEO/지역 검색 노출에 중요하다.\n- 나머지는 업체명, 핵심 서비스/상품명, 시술·시공 종류, 원고의 핵심 주제를 반영한 롱테일 키워드로 채워라.\n- 너무 비슷한 의미의 태그가 겹치지 않게 다양하게 골라라.\n- 특이사항에서 다른 개수를 요구하지 않았다면 기본으로 정확히 10개를 골라라.\n\n원고:\n"+text.slice(0,4000);
  var d=await sample.json(prompt,{cache:false,modelTier:"quick"});
  return(d.tags||[]).map(function(t){return(t||"").replace(/^#+/,"").replace(/\s+/g,"").trim()}).filter(Boolean).slice(0,80);
}
function qAll(root,name){
  var out=[],all=root.getElementsByTagName("*");
  for(var i=0;i<all.length;i++){if(all[i].localName===name)out.push(all[i])}
  return out;
}
async function parseHwpxFile(file){
  var buf=await file.arrayBuffer();
  var zip=await JSZip.loadAsync(buf);
  var headerEntry=null,sectionEntries=[];
  zip.forEach(function(path,entry){
    if(/header\.xml$/i.test(path))headerEntry=entry;
    else if(/section\d+\.xml$/i.test(path))sectionEntries.push({path:path,entry:entry});
  });
  if(!headerEntry||!sectionEntries.length)throw new Error("hwpx 구조를 인식할 수 없어요(구버전 .hwp일 수 있어요)");
  sectionEntries.sort(function(a,b){
    var na=parseInt((a.path.match(/section(\d+)\.xml$/)||[])[1]||"0",10);
    var nb=parseInt((b.path.match(/section(\d+)\.xml$/)||[])[1]||"0",10);
    return na-nb;
  });
  var parser=new DOMParser();
  var headerXml=await headerEntry.async("string");
  var headerDoc=parser.parseFromString(headerXml,"application/xml");
  var charMap={};
  qAll(headerDoc,"charPr").forEach(function(cp){
    var id=cp.getAttribute("id");
    var bold=qAll(cp,"bold").length>0;
    var underline=false;
    qAll(cp,"underline").forEach(function(u){
      var t=u.getAttribute("type");
      if(t&&t!=="NONE")underline=true;
    });
    charMap[id]={bold:bold,underline:underline};
  });
  var lines=[];
  for(var si=0;si<sectionEntries.length;si++){
    var xml=await sectionEntries[si].entry.async("string");
    var doc=parser.parseFromString(xml,"application/xml");
    qAll(doc,"p").forEach(function(p){
      var lineParts=[];
      qAll(p,"run").forEach(function(r){
        var ref=r.getAttribute("charPrIDRef");
        var fmt=charMap[ref]||{bold:false,underline:false};
        var txt=qAll(r,"t").map(function(t){return t.textContent||""}).join("");
        if(!txt)return;
        txt=txt.replace(/[{}]/g,"");
        if(fmt.bold&&fmt.underline)lineParts.push("{bu:"+txt+"}");
        else if(fmt.bold)lineParts.push("{b:"+txt+"}");
        else if(fmt.underline)lineParts.push("{u:"+txt+"}");
        else lineParts.push(txt);
      });
      lines.push(lineParts.join(""));
    });
  }
  return lines.join("\n");
}

/* ================= 화면 상태 ================= */
var CUR={};            // 지금 처리 중인 원고의 프리셋 스타일 (AI 지시문이 참조)
var PRESETS={};        // 서버(동기화 파일)에 저장된 프리셋
var SETTINGS={};
var currentName="";    // 선택된 프리셋 이름
var ITEMS=[];          // 원고 목록
var SEL=null;          // 선택된 원고 id
var seq=0,running=false,stopReq=false;
var DEFAULTS=null;

function get(){var o={};F.forEach(function(k){var e=$(k);o[k]=e.type==="checkbox"?e.checked:e.value});return o}
function set(o){F.forEach(function(k){if(o[k]===undefined||o[k]===null)return;var e=$(k);if(e.type==="checkbox")e.checked=!!o[k];else e.value=o[k]})}
function render(){renderSwatches();renderSelected()}

function copyText(s){
  try{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s);return true}}catch(e){}
  try{var ta=document.createElement("textarea");ta.value=s;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.select();var ok=document.execCommand("copy");document.body.removeChild(ta);return ok}catch(e){return false}
}
var toastTimer=null;
function showToast(msg){var t=$("toast");t.textContent=msg;t.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.classList.remove("show")},1800)}

/* ---------- 잠금 / 동기화 ---------- */
async function loadState(){
  var st=await api("/api/state");
  var s=st.store;
  $("verInfo").textContent="버전 "+st.version+(st.platform==="mac"?" (맥)":st.platform==="win"?" (윈도우)":"");
  $("syncPath").textContent=s.syncDir||"(지정 안 됨)";
  if(!s.unlocked){showLock(s);return false}
  $("lockOv").classList.remove("on");
  $("syncChip").textContent="구글 드라이브 동기화 중";$("syncChip").classList.add("ok");
  PRESETS=st.presets||{};SETTINGS=st.settings||{};
  $("keyBanner").style.display=SETTINGS.hasGeminiKey?"none":"block";
  $("previewFirst").checked=!!SETTINGS.previewBeforeUpload;
  fillPl();
  return true;
}
function showLock(s){
  var exists=s.syncDir&&s.fileExists;
  $("lockOv").classList.add("on");
  $("setupBox").style.display=exists?"none":"";
  $("lockTitle").textContent=exists?"동기화 비밀번호 입력":"처음 설정";
  $("masterLabel").textContent=exists?"동기화 비밀번호":"동기화 비밀번호 정하기";
  $("masterHelp").style.display=exists?"none":"";
  var sel=$("candSel");sel.innerHTML="";
  (s.candidates||[]).forEach(function(c){var o=document.createElement("option");o.value=o.textContent=c;sel.appendChild(o)});
  var o=document.createElement("option");o.value="";o.textContent=(s.candidates||[]).length?"직접 입력":"구글 드라이브를 찾지 못했어요 — 아래에 직접 입력";sel.appendChild(o);
  $("syncDir").value=s.syncDir||(s.candidates||[])[0]||"";
  $("noDriveHelp").style.display=(s.candidates||[]).length?"none":"block";
  sel.onchange=function(){if(sel.value)$("syncDir").value=sel.value};
  $("syncChip").textContent="잠김";$("syncChip").classList.remove("ok");
  setTimeout(function(){$("master").focus()},50);
}
$("lockGo").onclick=async function(){
  $("lockErr").textContent="";
  var m=$("master").value;if(!m){$("lockErr").textContent="비밀번호를 입력하세요.";return}
  try{
    if($("setupBox").style.display==="none")await api("/api/unlock",{master:m,remember:$("remember").checked});
    else{
      var d=$("syncDir").value.trim();if(!d){$("lockErr").textContent="동기화 폴더를 입력하세요.";return}
      await api("/api/setup",{syncDir:d,master:m,remember:$("remember").checked});
    }
    $("master").value="";
    await loadState();
    showToast("동기화 폴더에 연결됐어요");
  }catch(e){$("lockErr").textContent=e.message}
};
$("pickFolder").onclick=async function(){
  try{var d=await api("/api/pick-folder",{});if(d.path){$("syncDir").value=d.path;$("candSel").value=""}}
  catch(e){$("lockErr").textContent=e.message}
};
$("master").addEventListener("keydown",function(e){if(e.key==="Enter")$("lockGo").click()});

/* ---------- 프리셋 ---------- */
function fillPl(){
  var s=$("pl"),cur=currentName;s.innerHTML='<option value="">프리셋 선택</option>';
  Object.keys(PRESETS).sort(function(a,b){return a.localeCompare(b,"ko")}).forEach(function(n){
    var o=document.createElement("option");o.value=n;
    var a=PRESETS[n].account||{};
    o.textContent=n+(a.id&&a.hasPw?"":" (계정 없음)");s.appendChild(o);
  });
  s.value=cur&&PRESETS[cur]?cur:"";
}
function setLocked(state){
  $("lockArea").classList.toggle("locked",state);
  $("lockArea").querySelectorAll("input,select,textarea,button").forEach(function(e){e.disabled=state});
  $("lockMsg").style.display=state?"":"none";
  if(!state)$("runAll").disabled=running;
}
function loadPreset(name){
  var p=PRESETS[name];
  if(!p){currentName="";$("pn").value="";$("note").value="";$("memo").value="";$("accId").value="";$("accPw").value="";$("accBlog").value="";setLocked(true);return}
  set(DEFAULTS);set(p);currentName=name;
  $("pn").value=name;$("pl").value=name;
  $("note").value=p.note||"";$("memo").value=p.memo||"";
  var a=p.account||{};
  $("accId").value=a.id||"";$("accBlog").value=a.blogId||"";$("accPw").value="";
  $("accPw").placeholder=a.hasPw?"저장됨 (바꿀 때만 입력)":"비밀번호";
  if(p.mode==="head")showToast("이 프리셋은 '카페' 형식이었어요. 이 프로그램은 블로그 형식으로 꾸며요.");
  setLocked(false);render();
}
$("pl").onchange=function(){loadPreset(this.value)};
$("ps").onclick=async function(){
  var n=$("pn").value.trim();if(!n){showToast("클라이언트 이름을 입력하세요");return}
  var acc={id:$("accId").value,blogId:$("accBlog").value};
  if($("accPw").value)acc.pw=$("accPw").value;
  try{
    var d=await api("/api/preset/save",{name:n,oldName:currentName&&currentName!==n&&PRESETS[currentName]&&confirm("'"+currentName+"' 프리셋 이름을 '"+n+"'(으)로 바꿀까요?\n(취소를 누르면 새 프리셋으로 복사돼요)")?currentName:null,style:get(),account:acc});
    PRESETS=d.presets;currentName=n;fillPl();loadPreset(n);showToast("프리셋이 저장됐어요 (다른 컴퓨터에도 동기화)");
  }catch(e){showToast(e.message)}
};
$("pnew").onclick=function(){
  set(DEFAULTS);currentName="";$("pl").value="";
  ["pn","note","memo","accId","accPw","accBlog"].forEach(function(k){$(k).value=""});
  $("accPw").placeholder="비밀번호";setLocked(false);render();$("pn").focus();
};
$("pd").onclick=async function(){
  var n=$("pl").value;if(!n)return;
  if(!confirm("'"+n+"' 프리셋을 삭제할까요? (다른 컴퓨터에서도 삭제돼요)"))return;
  try{var d=await api("/api/preset/delete",{name:n});PRESETS=d.presets;loadPreset("");fillPl()}catch(e){showToast(e.message)}
};
F.forEach(function(k){var e=$(k);if(e.type!=="hidden"){e.addEventListener("input",render);e.addEventListener("change",render)}});
$("use2").addEventListener("change",function(){$("swid").value="";if(!this.checked){$("kc2").value="#3a6ab5"}render()});
["kc","hl","kc2"].forEach(function(id){$(id).addEventListener("input",function(){$("swid").value=""})});

/* ---------- 프리셋 파일 가져오기 / 내보내기 ---------- */
$("pimp").onclick=function(){$("pimpIn").click()};
$("pimpIn").onchange=async function(){
  var f=this.files&&this.files[0];this.value="";if(!f)return;
  try{
    var text=(await f.text()).replace(/^\uFEFF/,"");
    var data;try{data=JSON.parse(text)}catch(e){throw new Error("파일 형식을 읽을 수 없어요 (프리셋 내보내기 파일이나 기존 도구의 프리셋 파일을 넣어 주세요)")}
    var overwrite=Object.keys(PRESETS).length?confirm("이미 있는 같은 이름의 프리셋도 파일 내용으로 덮어쓸까요?\n(확인: 덮어쓰기 / 취소: 새 프리셋만 추가)\n계정 정보는 그대로 유지돼요."):true;
    var d=await api("/api/preset/import",{data:data,overwrite:overwrite});
    PRESETS=d.presets;fillPl();showToast("프리셋 "+d.count+"개를 가져왔어요");
  }catch(e){showToast(e.message)}
};
$("pexp").onclick=async function(){
  try{
    var d=await api("/api/preset/export",{});
    var blob=new Blob([JSON.stringify(d,null,1)],{type:"application/json"});
    var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="프리셋_내보내기.json";document.body.appendChild(a);a.click();a.remove();
    showToast("계정 정보를 뺀 프리셋을 파일로 저장했어요");
  }catch(e){showToast(e.message)}
};

/* ---------- 원고 파일 ---------- */
function addItem(name,text){
  if(!currentName){showToast("먼저 프리셋을 선택하세요");return}
  var it={id:++seq,file:name,text:text,preset:currentName,status:"대기",title:"",tags:[],html:"",err:""};
  var sp=splitText(text);it.title=guessTitle(sp.meta,name);
  ITEMS.push(it);if(!SEL)SEL=it.id;renderItems();renderSelected();
}
async function readFile(f){
  if(/\.hwpx$/i.test(f.name))return await parseHwpxFile(f);
  if(/\.hwp$/i.test(f.name))throw new Error("구버전 .hwp는 지원하지 않아요. hwpx로 저장해주세요.");
  var buf=await f.arrayBuffer();
  try{return new TextDecoder("utf-8",{fatal:true}).decode(buf).replace(/^﻿/,"")}
  catch(e){return new TextDecoder("euc-kr").decode(buf)}
}
async function addFiles(files){
  for(var i=0;i<files.length;i++){
    try{var t=await readFile(files[i]);if(!t.trim())throw new Error("내용이 비어 있어요");addItem(files[i].name,t.replace(/\r\n?/g,"\n"))}
    catch(e){showToast(files[i].name+": "+e.message)}
  }
}
$("drop").onclick=function(){$("fileIn").click()};
$("fileIn").onchange=function(){var fs=Array.prototype.slice.call(this.files);this.value="";addFiles(fs)};
["dragenter","dragover"].forEach(function(ev){$("drop").addEventListener(ev,function(e){e.preventDefault();$("drop").classList.add("over")})});
["dragleave","drop"].forEach(function(ev){$("drop").addEventListener(ev,function(e){e.preventDefault();$("drop").classList.remove("over")})});
$("drop").addEventListener("drop",function(e){addFiles(Array.prototype.slice.call(e.dataTransfer.files))});
$("pasteAdd").onclick=function(){var t=$("pasteIn").value;if(!t.trim())return;addItem("붙여넣은 원고 "+(seq+1),t);$("pasteIn").value=""};

var BADGE={"대기":"","AI 꾸미는 중":"run","확인 대기":"run","업로드 대기":"run","업로드 중":"run","완료":"ok","실패":"err","취소":"err"};
function renderItems(){
  var box=$("items");box.innerHTML="";
  ITEMS.forEach(function(it){
    var d=document.createElement("div");d.className="item"+(it.id===SEL?" sel":"");
    d.innerHTML='<span class="nm"></span><span class="mut" style="margin:0"></span><span class="badge '+(BADGE[it.status]||"")+'"></span><button class="g" style="padding:2px 8px;font-size:12px">✕</button>';
    d.querySelector(".nm").textContent=it.file+" — "+(it.title||"");
    d.querySelector(".mut").textContent=it.preset;
    d.querySelector(".badge").textContent=it.status;
    d.onclick=function(){SEL=it.id;renderItems();renderSelected()};
    d.querySelector("button").onclick=function(e){e.stopPropagation();if(it.status==="AI 꾸미는 중"||it.status==="업로드 중")return;ITEMS=ITEMS.filter(function(x){return x!==it});if(SEL===it.id)SEL=ITEMS.length?ITEMS[0].id:null;renderItems();renderSelected()};
    box.appendChild(d);
  });
}
function selItem(){return ITEMS.find(function(x){return x.id===SEL})}
function renderSelected(){
  var it=selItem();
  if(!it){$("out").innerHTML='<p style="color:#999;text-align:center">원고를 선택하면 미리보기가 보여요</p>';$("title").value="";$("tags").innerHTML="";$("tagMsg").textContent="";$("itemErr").textContent="";return}
  $("title").value=it.title||"";
  $("itemErr").textContent=it.err||"";
  var box=$("tags");box.innerHTML="";
  (it.tags||[]).forEach(function(t){var b=document.createElement("button");b.type="button";b.className="tagchip";b.textContent="#"+t;b.title="클릭하면 이 태그를 빼요";b.onclick=function(){it.tags=it.tags.filter(function(x){return x!==t});rebuildHTML(it);renderSelected()};box.appendChild(b)});
  $("tagMsg").textContent=it.tags&&it.tags.length?(it.tagsFromText?"원고에 있던 해시태그를 그대로 썼어요.":"AI가 만든 해시태그예요. 클릭하면 빠져요."):(it.status==="대기"?"실행하면 만들어져요.":"");
  if(it.html){$("out").innerHTML=it.html}
  else{ // 꾸미기 전: 원고 서식만 적용한 미리보기
    var st=it.preset===currentName?get():(PRESETS[it.preset]||get());
    var sp=splitText(it.text);CUR=st;sp.body=applyQuoteMarkers(sp.body);sp.body=applyTableMarker(sp.body);
    $("out").innerHTML=renderHTML(st,sp.body,null);
  }
  var busy=it.status==="AI 꾸미는 중"||it.status==="업로드 중"||it.status==="업로드 대기";
  $("uploadOne").disabled=busy||!it.html;$("redoOne").disabled=busy;
}
$("title").addEventListener("input",function(){var it=selItem();if(it)it.title=this.value;renderItems()});

/* ---------- 처리 파이프라인 ---------- */
function nn(o){var r={};Object.keys(o||{}).forEach(function(k){if(o[k]!==null&&o[k]!==undefined)r[k]=o[k]});return r}
function styleFor(it){return it.preset===currentName?Object.assign({},nn(PRESETS[it.preset]),get()):Object.assign({},DEFAULTS,nn(PRESETS[it.preset]))}
function rebuildHTML(it){
  var c=styleFor(it);
  it.html=renderHTML(c,it.body,it.tagsFromText?null:(SETTINGS.tagMode==="dialog"?null:it.tags));
}
async function decorate(it){
  var c=styleFor(it);CUR=c;
  it.status="AI 꾸미는 중";it.err="";renderItems();if(it.id===SEL)renderSelected();
  var sp=splitText(it.text);
  sp.body=applyQuoteMarkers(sp.body);sp.body=applyTableMarker(sp.body);
  var existing=extractExistingTags(it.text);
  var tags=existing.length?existing:await generateTags(sample,sp,(c.note||"").trim()).catch(function(e){it.err="태그 생성 실패: "+e.message;return[]});
  CUR=c;
  it.body=await aiMarks(sp);
  it.tags=tags||[];it.tagsFromText=!!existing.length;
  rebuildHTML(it);
}
function plainOf(html){var d=document.createElement("div");d.innerHTML=html;document.body.appendChild(d);var t=d.innerText;d.remove();return t}
async function upload(it){
  var acc=(PRESETS[it.preset]||{}).account||{};
  if(!acc.id||!acc.hasPw)throw new Error("'"+it.preset+"' 프리셋에 네이버 아이디/비밀번호를 먼저 저장하세요.");
  var tags=SETTINGS.tagMode==="body"?[]:it.tags;
  var r=await api("/api/upload",{preset:it.preset,title:it.title,html:it.html,plain:plainOf(it.html),tags:tags,file:it.file});
  it.jobId=r.id;it.status="업로드 대기";renderItems();
}
$("runAll").onclick=async function(){
  if(running)return;
  if(!SETTINGS.hasGeminiKey){showToast("⚙ 설정에서 Gemini API 키를 먼저 넣어 주세요");openSettings();return}
  if(currentName&&PRESETS[currentName]){try{var d=await api("/api/preset/save",{name:currentName,style:get(),account:null});PRESETS=d.presets}catch(e){}}
  var todo=ITEMS.filter(function(x){return x.status==="대기"||x.status==="실패"||x.status==="취소"});
  if(!todo.length){showToast("실행할 원고가 없어요");return}
  running=true;stopReq=false;$("runAll").disabled=true;
  var preview=$("previewFirst").checked;
  for(var i=0;i<todo.length&&!stopReq;i++){
    var it=todo[i];
    try{
      if(!it.html||it.status!=="실패")await decorate(it);
      if(stopReq){it.status="취소";break}
      if(preview){it.status="확인 대기"}else{await upload(it)}
    }catch(e){it.status="실패";it.err=e.message}
    renderItems();if(it.id===SEL||!SEL){SEL=it.id;renderItems()}renderSelected();
  }
  running=false;$("runAll").disabled=false;
  if(preview)showToast("미리보기를 확인하고 원고마다 [이 원고 업로드]를 눌러 주세요");
};
$("uploadOne").onclick=async function(){var it=selItem();if(!it)return;try{await upload(it)}catch(e){it.err=e.message;renderSelected()}};
$("redoOne").onclick=async function(){
  var it=selItem();if(!it||running)return;
  try{await decorate(it);it.status="확인 대기"}catch(e){it.status="실패";it.err=e.message}
  renderItems();renderSelected();
};
$("stopAll").onclick=async function(){stopReq=true;try{await api("/api/stop",{})}catch(e){}showToast("중지 요청했어요. 진행 중인 단계가 끝나면 멈춰요.")};
$("clearDone").onclick=function(){ITEMS=ITEMS.filter(function(x){return x.status!=="완료"});if(!selItem())SEL=ITEMS.length?ITEMS[0].id:null;renderItems();renderSelected()};
$("cp").onclick=function(){
  var d=$("out"),r=document.createRange();r.selectNodeContents(d);
  var g=window.getSelection();g.removeAllRanges();g.addRange(r);
  var ok=false;try{ok=document.execCommand("copy")}catch(e){}g.removeAllRanges();
  showToast(ok?"복사됐어요! 블로그 에디터에 붙여넣을 수 있어요.":"복사 실패");
};
$("previewFirst").onchange=function(){api("/api/settings",{previewBeforeUpload:this.checked}).catch(function(){})};

/* ---------- 업로드 진행 상황 ---------- */
async function pollJobs(){
  try{
    var d=await api("/api/jobs");
    var lines=[];
    d.jobs.forEach(function(j){
      lines.push("["+j.status+"] "+j.preset+" · "+j.title);
      (j.log||[]).forEach(function(l){lines.push("    "+l)});
      var it=ITEMS.find(function(x){return x.jobId===j.id});
      if(it){
        var ns=j.status==="대기"?"업로드 대기":j.status==="진행 중"?"업로드 중":j.status;
        if(it.status!==ns){it.status=ns;it.err=j.error||"";renderItems();if(it.id===SEL)renderSelected()}
      }
    });
    if(lines.length){var el=$("log"),atEnd=el.scrollTop+el.clientHeight>=el.scrollHeight-10;el.textContent=lines.join("\n");if(atEnd)el.scrollTop=el.scrollHeight}
  }catch(e){}
  setTimeout(pollJobs,1500);
}
$("openLogs").onclick=function(){api("/api/open",{what:"logs"})};

/* ---------- 설정 ---------- */
function openSettings(){
  $("setErr").textContent="";$("gkey").value="";
  $("gkey").placeholder=SETTINGS.hasGeminiKey?"저장됨 (바꿀 때만 입력)":"AIza로 시작하는 키";
  var m=$("model");m.innerHTML="";var o=document.createElement("option");o.value=o.textContent=SETTINGS.model||"gemini-flash-latest";m.appendChild(o);
  $("tagMode").value=SETTINGS.tagMode||"both";$("browser").value=SETTINGS.browser||"auto";
  $("setOv").classList.add("on");
}
$("settingsBtn").onclick=openSettings;
$("setClose").onclick=function(){$("setOv").classList.remove("on")};
$("loadModels").onclick=async function(){
  $("setErr").textContent="";
  try{
    var d=await api("/api/models",{key:$("gkey").value.trim()});
    var m=$("model"),cur=m.value;m.innerHTML="";
    d.models.filter(function(x){return /gemini/.test(x)}).forEach(function(x){var o=document.createElement("option");o.value=o.textContent=x;m.appendChild(o)});
    if([].some.call(m.options,function(o){return o.value===cur}))m.value=cur;
    showToast("모델 "+m.options.length+"개를 불러왔어요. 이름에 flash가 들어간 모델이 무료 등급에 알맞아요.");
  }catch(e){$("setErr").textContent=e.message}
};
$("setSave").onclick=async function(){
  try{
    var d=await api("/api/settings",{geminiKey:$("gkey").value.trim()||undefined,model:$("model").value,tagMode:$("tagMode").value,browser:$("browser").value});
    SETTINGS=d.settings;$("keyBanner").style.display=SETTINGS.hasGeminiKey?"none":"block";
    $("setOv").classList.remove("on");showToast("설정을 저장했어요");
  }catch(e){$("setErr").textContent=e.message}
};
$("openSync").onclick=function(){api("/api/open",{what:"sync"})};
$("lockBtn").onclick=async function(){
  if(!confirm("이 컴퓨터에 기억된 동기화 비밀번호를 지우고 잠글까요?"))return;
  await api("/api/lock",{});$("setOv").classList.remove("on");loadState();
};

/* ---------- 시작 ---------- */
async function checkUpdate(){
  try{var d=await api("/api/update");if(d.release&&d.release.newer){var b=$("updateBanner");b.innerHTML="";var a=document.createElement("a");a.href=d.release.url;a.target="_blank";a.textContent="새 버전 "+d.release.version+" 내려받기";b.append("새 버전이 나왔어요. ",a," (윈도우·맥 같은 버전으로 맞춰 주세요)");b.style.display="block"}}catch(e){}
}
setInterval(function(){api("/api/ping",{}).catch(function(){})},5000);
setInterval(async function(){ // 다른 컴퓨터에서 바뀐 프리셋 반영
  if(document.hidden)return;
  try{var st=await api("/api/state");if(st.presets){PRESETS=st.presets;SETTINGS=st.settings;fillPl()}}catch(e){}
},20000);
DEFAULTS=get();
setLocked(true);renderSwatches();
loadState();pollJobs();checkUpdate();
