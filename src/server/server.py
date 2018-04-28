import os
import json
import time
import asyncio
import shutil

db = json.load(open('db.json'))

LIMIT_N = 1
LIMIT_DURATION = 23*60*60

async def handle(reader, writer):
    print('connected')
    bi = (await reader.readline()).strip()
    if not bi:
        return
    bi = bi.decode('utf8')
    print('BI:',bi)

    if len(bi) > 200:
        writer.write(b'Invalid Bundle Identifier.\n')
        print('invalid bi')
        await writer.drain()
        return

    if bi not in db:
        db[bi] = []
    idx = 0
    t = time.time()
    while idx < len(db[bi]) and db[bi][idx] + LIMIT_DURATION < t:
        idx += 1
    db[bi] = db[bi][idx:]
    if len(db[bi]) >= LIMIT_N:
        writer.write(b'Daily limit exceeded. (1 per day)\n')
        print('Daily limit')
        await writer.drain()
        if idx > 0:
            json.dump(db, open('db.json','w'))
        return
    writer.write(b'\n')
    await writer.drain()


    sz = int((await reader.readline()).strip())
    print('ZIP size:',sz)

    # 512M
    if sz > 512*1024*1024: 
        writer.write(b'Too large zip file (500MB).\n')
        print('Too large')
        await writer.drain()
        return

    writer.write(b'\n')
    await writer.drain()

    db[bi].append(t)
    json.dump(db, open('db.json','w'))
    print('Accepted')

    folder = bi.replace('/', '_')
    try:
        os.makedirs(folder)
    except:
        pass

    upload_fname = os.path.join(folder, 'upload.zip')
    f = open(upload_fname,'wb')
    tsz = sz
    while sz > 0:
        chunk_size = min(65536,sz)
        chunk = await reader.read(chunk_size)
        f.write(chunk)
        sz -= len(chunk)
        print('\t',bi,'recv',tsz-sz, '/',tsz, end='\r')
    f.close()

    print('\t',bi,"unzip")
    p = await asyncio.create_subprocess_shell('cd '+folder+' && unzip -oq upload.zip')
    await p.wait()
    print('\t',bi,"perf script")
    p = await asyncio.create_subprocess_shell('cd '+folder+' && perf script', stdout = open(os.path.join(folder,'out.perf'), 'wb'))
    await p.wait()
    print('\t',bi,"stack collapse")
    p = await asyncio.create_subprocess_shell('cd '+folder+' && perl ../FlameGraph-master/stackcollapse-perf.pl out.perf', stdout = open(os.path.join(folder,'out.folded'), 'wb'))
    await p.wait()
    print('\t',bi,"flamegraph")
    p = await asyncio.create_subprocess_shell('cd '+folder+' && perl ../FlameGraph-master/flamegraph.pl out.folded', stdout=open(os.path.join(folder,'flamegraph.svg'),'wb'))
    await p.wait()
    print('\t',bi,"rm-rf")
    p = await asyncio.create_subprocess_shell('cd '+folder+' && rm -rf binary_cache perf.data out.perf out.folded')
    await p.wait()

    sz = os.stat(os.path.join(folder, 'flamegraph.svg')).st_size
    print(sz)
    writer.write((str(sz)+'\n').encode('utf8'))
    await writer.drain()
    tsz = sz
    with open(os.path.join(folder,'flamegraph.svg'),'rb') as f:
        while sz>0:
            chunk_size = min(sz, 65536)
            chunk = f.read(chunk_size)
            writer.write(chunk)
            await writer.drain()
            sz -= len(chunk)
            print('\t',bi,'send',tsz-sz, '/',tsz,end='\r')

    writer.close()

loop = asyncio.get_event_loop()
coro = asyncio.start_server(handle, '0.0.0.0', 40041, loop=loop)
server = loop.run_until_complete(coro)

# Serve requests until Ctrl+C is pressed
print('Serving on {}'.format(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

# Close the server
server.close()
loop.run_until_complete(server.wait_closed())
loop.close()
