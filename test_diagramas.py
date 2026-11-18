"""Pruebas del recorrido de reglas R01-R27 y de sus decisiones condicionales.
Ejecutar: python -m unittest test_diagramas.py (requiere requirements.txt)."""
import unittest
from datos import RepositorioConocimiento
from negocio import MotorDJ

class DiagramaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = MotorDJ(RepositorioConocimiento())

    def evaluar(self, hechos, aclaraciones=None):
        return self.motor.recomendar(hechos, [], aclaraciones=aclaraciones)

    def test_27_reglas_cargadas(self):
        self.assertEqual([r['codigo'] for r in self.motor.reglas], [f'R{i:02}' for i in range(1,28)])

    def test_boda_cierre_adultos_pop_negativa(self):
        r=self.evaluar(dict(tipo_evento='boda',momento='cierre',grupo_edad='adultos',genero_actual='pop',reaccion_publico='negativa'))
        self.assertEqual([x['codigo'] for x in r['reglas_disparadas']],['R02','R11','R15','R24'])

    def test_discoteca_desarrollo_jovenes_pop_baile(self):
        r=self.evaluar(dict(tipo_evento='discoteca',momento='desarrollo',grupo_edad='jovenes',genero_actual='pop',reaccion_publico='baila_y_canta'))
        self.assertEqual([x['codigo'] for x in r['reglas_disparadas']],['R05','R09','R14','R19'])

    def test_r20_no_sube_sin_confirmar(self):
        h=dict(genero_actual='salsa',reaccion_publico='baila_poco',momento='desarrollo')
        self.assertIn('CONSULTAR',[r['accion'] for r in self.evaluar(h)['recomendaciones']])
        self.assertIn('SUBIR_ENERGIA',[r['accion'] for r in self.evaluar(h,{'actividad_baile':'si'})['recomendaciones']])
        self.assertNotIn('SUBIR_ENERGIA',[r['accion'] for r in self.evaluar(h,{'actividad_baile':'no'})['recomendaciones']])

    def test_r21_consulta_antes_de_cambiar(self):
        h=dict(genero_actual='rock',reaccion_publico='sentado')
        self.assertIn('CONSULTAR',[r['accion'] for r in self.evaluar(h)['recomendaciones']])
        self.assertIn('BAJAR_O_COMERCIAL',[r['accion'] for r in self.evaluar(h,{'publico_desea_bailar':'si'})['recomendaciones']])

    def test_r25_consulta_causa(self):
        h=dict(genero_actual='merengue',reaccion_publico='sin_reaccion')
        self.assertIn('CONSULTAR',[r['accion'] for r in self.evaluar(h)['recomendaciones']])
        self.assertIn('BUSCAR_OTRA',[r['accion'] for r in self.evaluar(h,{'causa_sin_reaccion':'rechaza_cancion'})['recomendaciones']])
        self.assertIn('BAJAR_ENERGIA',[r['accion'] for r in self.evaluar(h,{'causa_sin_reaccion':'menos_intensidad'})['recomendaciones']])

    def test_r10_actividad(self):
        h={'momento':'momento_principal'}
        self.assertNotIn('SUBIR_ENERGIA',[r['accion'] for r in self.evaluar(h)['recomendaciones']])
        self.assertIn('SUBIR_ENERGIA',[r['accion'] for r in self.evaluar(h,{'actividad_principal':'si'})['recomendaciones']])

    def test_retirada(self):
        h={'momento':'cierre','reaccion_publico':'se_retira'}
        self.assertEqual([r['codigo'] for r in self.evaluar(h)['reglas_disparadas']],['R11','R26'])
        h['momento']='inicio'
        self.assertEqual([r['codigo'] for r in self.evaluar(h)['reglas_disparadas']],['R08','R27'])

    def test_rechaza_aclaracion_desconocida(self):
        with self.assertRaises(ValueError): self.evaluar({'momento':'cierre'},{'inventada':'si'})

if __name__=='__main__': unittest.main()
