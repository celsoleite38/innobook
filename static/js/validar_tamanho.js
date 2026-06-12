document.addEventListener('DOMContentLoaded', function () {
    // Busca todos os campos de upload de arquivo da página
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(function (input) {
        input.addEventListener('change', function () {
            if (this.files && this.files[0]) {
                const arquivo = this.files[0];
                const tamanhoMaximo = 10 * 1024 * 1024; // 10 MB em Bytes
                
                if (arquivo.size > tamanhoMaximo) {
                    // Exibe o popup de erro
                    alert(`O arquivo "${arquivo.name}" é muito grande!\nO limite máximo permitido é de 10 MB. O seu arquivo tem ${(arquivo.size / (1024 * 1024)).toFixed(2)} MB.`);
                    
                    // Limpa o campo para travar o upload
                    this.value = '';
                }
            }
        });
    });
});