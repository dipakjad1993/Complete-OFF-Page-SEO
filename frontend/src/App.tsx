import { ThemeProvider } from './context/ThemeContext';
import ToolApp from './pages/ToolApp';

function App() {
  return (
    <ThemeProvider>
      <ToolApp />
    </ThemeProvider>
  );
}

export default App;
