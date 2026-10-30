// Lanceur Windows.
//   MyBGRemover.exe --serveur : démarre le serveur sans fenêtre (ouverture de session Windows).
//   MyBGRemover.exe           : idem, puis ouvre l'app installée (PWA de Chrome), sinon la page
//                               dans le navigateur, d'où on l'installe.
// Le serveur reste léger tant qu'on ne détoure pas (cf. app/serveur.py). Compilé par
// lanceur\construire.bat.

using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

static class Lanceur
{
    const string Adresse = "http://127.0.0.1:8765/";
    const string Titre = "MyBGRemover";

    static bool Repond()
    {
        try
        {
            var requete = (HttpWebRequest)WebRequest.Create(Adresse + "api/etat");
            requete.Timeout = 1000;
            requete.Proxy = null;
            using (requete.GetResponse()) return true;
        }
        catch (WebException) { return false; }
    }

    static Process DemarrerServeur(string racine, string python)
    {
        var info = new ProcessStartInfo(python, "-m uvicorn app.serveur:app --host 127.0.0.1 --port 8765 --log-level warning")
        {
            WorkingDirectory = racine,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        return Process.Start(info);
    }

    [STAThread]
    static void Main(string[] args)
    {
        bool serveurSeul = args.Length > 0 && args[0] == "--serveur";
        string racine = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(racine, @".venv\Scripts\python.exe");

        if (!Repond())
        {
            if (!File.Exists(python))
            {
                // premier lancement : l'installation se fait dans une fenêtre visible
                if (!serveurSeul)
                    Process.Start(new ProcessStartInfo(Path.Combine(racine, "lancer.bat")) { WorkingDirectory = racine });
                return;
            }
            var serveur = DemarrerServeur(racine, python);
            if (serveurSeul) return;

            var limite = DateTime.Now.AddSeconds(60);
            while (!Repond())
            {
                if (serveur.HasExited || DateTime.Now > limite)
                {
                    MessageBox.Show("Le serveur n'a pas démarré. Lance lancer.bat pour voir l'erreur.",
                        Titre, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                Thread.Sleep(300);
            }
        }
        if (serveurSeul) return;

        // raccourci créé par Chrome à l'installation de l'app
        string app = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), @"Chrome Apps\MyBGRemover.lnk");
        Process.Start(File.Exists(app) ? app : Adresse);
    }
}
