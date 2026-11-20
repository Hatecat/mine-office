// Sala mínima de ejemplo (no se usa en la oficina).
export const meta = { id: '_ejemplo', title: 'Ejemplo', size: [6, 5], floor: 'carpet', floorColor: '#5a6a9a' };
export default function build(V) {
  const g = new V.THREE.Group();
  g.add(V.box(2, 0.1, 1, V.MAT.darkwood, 3, 0.85, 1.5));
  g.userData.spots = [{ x: 3, z: 2.6, y: 0.5, rotY: Math.PI, pose: 'sit', activity: 'meeting' }, { x: 4.5, z: 3.5, y: 0, rotY: -Math.PI / 2, pose: 'stand', activity: 'chat' }];
  return g;
}
