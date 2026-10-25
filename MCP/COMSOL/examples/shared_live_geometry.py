"""Stage 1: review, then run on a dedicated empty Desktop-shared demo model."""
def run(context):
    from jpype import JArray, JString
    model=context['model']; m=model.java
    if list(m.component().tags()):
        raise ValueError('This geometry demo requires an empty dedicated model.')
    m.label('MCP_SHARED_LIVE_DEMO')
    for key,value in {'demo_L':'20[mm]','demo_W':'10[mm]','demo_H':'5[mm]','demo_P':'0.2[W]','demo_h':'15[W/(m^2*K)]','demo_Tamb':'298.15[K]','demo_stage':'1'}.items(): m.param().set(key,value)
    m.component().create('comp1',True); g=m.component('comp1').geom().create('geom1',3)
    g.lengthUnit('mm'); g.create('blk1','Block'); g.feature('blk1').label('MCP live block - stage 1')
    g.feature('blk1').set('size',JArray(JString)(['demo_L','demo_W','demo_H'])); g.run()
    return {'domains':int(g.getNDomains()),'boundaries':int(g.getNBoundaries()),'bounding_box_mm':[float(x) for x in g.getBoundingBox()]}
