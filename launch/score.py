"""Original, deterministic electronic score. No samples or external music assets."""
from pathlib import Path
import wave
import numpy as np

root=Path(__file__).resolve().parent
out=root/'film'/'audio';out.mkdir(exist_ok=True)
sr=22050;duration=90;n=sr*duration
audio=np.zeros(n,dtype=np.float64)
rng=np.random.default_rng(20261021)
beat=60/112

def add(start,data,gain=1):
    a=int(start*sr)
    if a<0:return
    length=min(len(data),n-a)
    if length>0:audio[a:a+length]+=gain*data[:length]

def tone(freq,length,pluck=True):
    t=np.arange(int(length*sr))/sr
    env=(1-np.exp(-t*40))*np.exp(-t*(5 if pluck else .65))
    return (np.sin(2*np.pi*freq*t)+.2*np.sin(2*np.pi*freq*2*t))*env

# D minor, Bb, F, C. Airy ninths and restrained syncopated plucks.
chords=[[146.832,174.614,220,261.626,329.628],[116.541,146.832,174.614,220,261.626],[130.813,164.814,196,261.626,293.665],[130.813,164.814,196,246.942,293.665]]
for bar in range(43):
    start=bar*4*beat;notes=chords[(bar//2)%4]
    if start>=duration:break
    density=.55 if 65<=start<77 else 1
    for note in notes:add(start,tone(note/2,3.2,False),.027*density)
    for j in [0,1.5,2.5,3.25]:add(start+j*beat,tone(notes[int(j*2)%len(notes)]*2,.65),.07*density)
    for j in [0,2]:
        t=np.arange(int(.27*sr))/sr
        phase=2*np.pi*(45*t+70*.03*(1-np.exp(-t/.03)))
        add(start+j*beat,np.sin(phase)*np.exp(-t*20),.24*density)
    for j in range(8):
        t=np.arange(int(.042*sr))/sr;noise=rng.standard_normal(len(t));high=np.diff(noise,prepend=0)
        add(start+j*.5*beat,high*np.exp(-t*90),.021*density)

# Three intended emphasis hits: identity, offline turn, beta offer.
for start in [6.5,65,77]:
    t=np.arange(int(.8*sr))/sr
    add(start,np.sin(2*np.pi*(52*t+90*.045*(1-np.exp(-t/.045))))*np.exp(-t*6),.30)
    add(start+.035,rng.standard_normal(len(t))*np.exp(-t*13),.035)

timeline=np.arange(n)/sr
duck=np.ones(n)
for start in [6.5,65,77]:
    duck[(timeline>start-.32)&(timeline<start-.02)]*=.25
audio*=duck*np.minimum(1,timeline/.4)*np.minimum(1,(duration-timeline)/.65)
audio=np.tanh(audio*1.35)
audio*=.79/max(np.max(np.abs(audio)),.01)
pcm=(audio*32767).astype('<i2')
with wave.open(str(out/'score.wav'),'wb') as wav:
    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(sr);wav.writeframes(pcm.tobytes())
print(out/'score.wav')
