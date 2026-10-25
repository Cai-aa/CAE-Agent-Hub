"""Stage 2: real solid heat transfer and mesh in the shared demo model."""
def run(context):
    from jpype import JArray,JString,JInt
    m=context['model'].java; c=m.component('comp1')
    if str(m.label())!='MCP_SHARED_LIVE_DEMO': raise ValueError('Dedicated demo model required.')
    if list(c.physics().tags()): raise ValueError('Demo physics already exists.')
    arr=lambda x:JArray(JString)(x)
    c.selection().create('bottom','Box'); s=c.selection('bottom'); s.set('entitydim',JInt(2)); s.set('condition','inside'); s.set('zmin','-0.001[mm]'); s.set('zmax','0.001[mm]')
    c.selection().create('external','Explicit'); c.selection('external').geom('geom1',2); c.selection('external').all()
    c.selection().create('conv','Difference'); s=c.selection('conv'); s.set('entitydim',JInt(2)); s.set('add',arr(['external'])); s.set('subtract',arr(['bottom']))
    c.material().create('mat1','Common'); mat=c.material('mat1'); mat.label('Aluminum - live shared demo'); mat.selection().all()
    for p,v in [('thermalconductivity','167[W/(m*K)]'),('density','2700[kg/m^3]'),('heatcapacity','900[J/(kg*K)]')]: mat.propertyGroup('def').set(p,arr([v]))
    c.physics().create('ht','HeatTransfer','geom1'); ht=c.physics('ht'); ht.feature('init1').set('Tinit','demo_Tamb')
    ht.create('hf1','HeatFluxBoundary',2); hf=ht.feature('hf1'); hf.selection().named('bottom'); hf.set('HeatFluxType','GeneralInwardHeatFlux'); hf.set('q0','demo_P/(demo_L*demo_W)')
    ht.create('hf2','HeatFluxBoundary',2); hf=ht.feature('hf2'); hf.selection().named('conv'); hf.set('HeatFluxType','ConvectiveHeatFlux'); hf.set('h','demo_h'); hf.set('Text','demo_Tamb')
    c.cpl().create('maxT','Maximum'); c.cpl('maxT').selection().geom('geom1',3); c.cpl('maxT').selection().all()
    mesh=c.mesh().create('mesh1'); mesh.autoMeshSize(JInt(4)); mesh.run()
    m.study().create('std1'); m.study('std1').label('Shared live stationary study'); m.study('std1').create('stat','Stationary')
    pg=m.result().create('pgtemp','PlotGroup3D'); pg.label('Shared live temperature (degC)'); pg.create('surf','Surface'); pg.feature('surf').set('expr','T'); pg.feature('surf').set('unit','degC')
    m.param().set('demo_stage','2')
    return {'physics_type':str(ht.getType()),'tetrahedra':int(mesh.getNumElem('tet')),'min_quality':float(mesh.getMinQuality('tet')),'heater_boundaries':[int(x) for x in c.selection('bottom').entities()],'convection_boundaries':[int(x) for x in c.selection('conv').entities()]}
