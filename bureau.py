"""Entry point for the Windows distribution, packaged with its Python runtime."""
import multiprocessing
import sys
from lancer import run

if __name__=="__main__":
    multiprocessing.freeze_support()
    if len(sys.argv)>1 and sys.argv[1]=="--restore":
        if len(sys.argv)!=4: sys.exit("Usage: VenturePublisher.exe --restore sauvegarde.zip nouveau-dossier")
        from restaurer import restore
        print("Restauration terminée :",restore(sys.argv[2],sys.argv[3]))
        sys.exit(0)
    sys.argv.insert(1,"--installed")
    run()
