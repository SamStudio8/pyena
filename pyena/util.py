# stolen from samstdio8/ocarina, nice one me
def hashfile(path, halg=hashlib.md5, bs=65536, force_hash=True):
    start_time = datetime.now()

    f = open(path, 'rb')
    buff = f.read(bs)
    halg = halg()
    halg.update(buff)
    b_hashed = bs
    while len(buff) > 0:
        buff = f.read(bs)
        halg.update(buff)
        b_hashed += bs
    f.close()

    ret = halg.hexdigest()

    end_time = datetime.now()
    hash_time = end_time - start_time
    #syslog.syslog('Hashed %s (~%.2fGB of %.2fGB in %s)' % (path, float(b_hashed) / 1e+9, float(os.path.getsize(path)) / 1e+9, str(hash_time)))

    return ret
