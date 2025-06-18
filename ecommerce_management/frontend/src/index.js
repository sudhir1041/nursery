const e = React.createElement;

function App() {
  return e('h1', null, 'Ecommerce Management Frontend');
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(e(App));
